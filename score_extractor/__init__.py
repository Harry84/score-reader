import os
import base64
import json
import logging
import mimetypes
import azure.functions as func
from io import BytesIO
import requests
import time
import anthropic

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-5"
MAX_RETRIES = 3
RETRY_DELAY = 5  # Increased retry delay to 5 seconds

def get_mime_type(file_path):
    """Determine the MIME type of a file based on its extension"""
    # Make sure mimetypes is initialized
    mimetypes.init()
    
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type and mime_type.startswith('image/'):
        return mime_type
    
    # Default to JPEG if we can't determine the type
    return 'image/jpeg'

def extract_scores_from_image(image_path):
    """
    Process a game score screen image with Claude API and extract structured data.
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        dict: Extracted scores as JSON
    """
    # Initialize the Anthropic client
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Read and encode the image
    try:
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
            base64_image = base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to read image file: {e}")
        raise ValueError(f"Could not process image at {image_path}: {str(e)}")
    
    # Get the MIME type for the image
    mime_type = get_mime_type(image_path)
    logger.info(f"Using MIME type: {mime_type} for image: {image_path}")
    
    # Create the prompt with the image and expected output format
    prompt = """
    Extract this Star Wars Squadrons score screen to a json. Pay close attention to the horizontal alignment such that the cap ship damage scores are attributed to the correct players and all the data from a row is kept together.  Also ensure that players are grouped by team even if not all 5 players are on a team.
    
    Please follow this exact format for the output:
    ```json
    {
      "match_result": "IMPERIAL VICTORY",
      "teams": {
        "imperial": {
          "players": [
            {
              "position": "Titan Four",
              "player": "playername1",
              "score": 1675,
              "kills": 0,
              "deaths": 2,
              "assists": 0,
              "ai_kills": 18,
              "cap_ship_damage": 30139
            },
            ...
          ]
        },
        "rebel": {
          "players": [
            {
              "position": "Vanguard Three",
              "player": "playername2",
              "score": 555,
              "kills": 0,
              "deaths": 1,
              "assists": 0,
              "ai_kills": 35,
              "cap_ship_damage": 0
            },
            ...
          ]
        }
      }
    }
    ```
    
    Return only the JSON with no additional text.
    """
    
    # Call the Claude API with retries
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Making API request attempt {attempt+1}/{MAX_RETRIES}")
            
            # Use the Anthropic client method
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": base64_image
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            )
            
            # Get the response text
            claude_response = message.content[0].text
            logger.info("API request successful")
            
            # Extract JSON from the response
            try:
                # Look for JSON content between ```json and ``` markers (standard for Claude)
                if "```json" in claude_response:
                    logger.info("Found JSON with ```json format")
                    json_start = claude_response.find("```json") + 7
                    json_end = claude_response.find("```", json_start)
                    json_str = claude_response[json_start:json_end].strip()
                # Also look for `json backtick format
                elif "`json" in claude_response:
                    logger.info("Found JSON with `json format")
                    json_start = claude_response.find("`json") + 5
                    json_end = claude_response.find("`", json_start)
                    json_str = claude_response[json_start:json_end].strip()
                # Or try to find just a raw JSON object
                elif claude_response.strip().startswith("{") and claude_response.strip().endswith("}"):
                    logger.info("Found raw JSON object")
                    json_str = claude_response.strip()
                else:
                    # As a fallback, try to find any JSON-like structure
                    logger.info("Attempting to extract JSON-like structure")
                    json_start = claude_response.find("{")
                    json_end = claude_response.rfind("}") + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = claude_response[json_start:json_end]
                    else:
                        logger.error("Could not find JSON in Claude's response")
                        raise ValueError("Could not find JSON in Claude's response")
                
                logger.info("Parsing extracted JSON")
                # Parse the extracted JSON
                extracted_data = json.loads(json_str)
                return extracted_data
            
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse JSON from Claude response: {e}")
                logger.debug(f"Claude response: {claude_response}")
                raise ValueError(f"Could not extract valid JSON from Claude's response: {str(e)}")
        
        except anthropic.APIError as e:
            logger.warning(f"API request failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Waiting {RETRY_DELAY} seconds before retrying...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"All API request attempts failed")
                raise RuntimeError(f"Failed to get response from Claude API: {str(e)}")

def extract_scores_from_multiple_images(image_paths):
    """
    Process multiple game score screen images with Claude API and extract structured data.
    
    Args:
        image_paths (list): List of paths to image files
        
    Returns:
        dict: Extracted scores for each image as JSON, keyed by filename
    """
    results = {}
    
    for image_path in image_paths:
        try:
            filename = os.path.basename(image_path)
            logger.info(f"Processing image: {filename}")
            
            result = extract_scores_from_image(image_path)
            results[filename] = result
            
            logger.info(f"Successfully processed {filename}")
        except Exception as e:
            logger.error(f"Error processing {image_path}: {str(e)}")
            results[os.path.basename(image_path)] = {"error": str(e)}
    
    return results

# Azure Function entry point
def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request must contain valid JSON"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # If it's a direct API call with base64 image
    if "image_base64" in req_body:
        try:
            # Decode base64 string to image
            image_data = base64.b64decode(req_body["image_base64"])
            
            # Save to temp file
            temp_image_path = "/tmp/temp_image.jpg"
            with open(temp_image_path, "wb") as temp_file:
                temp_file.write(image_data)
            
            # Process the image
            result = extract_scores_from_image(temp_image_path)
            
            # Clean up
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                
            return func.HttpResponse(
                json.dumps(result),
                status_code=200,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Error processing base64 image: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=500,
                mimetype="application/json"
            )
    
    # If it's multiple base64 images
    elif "images_base64" in req_body:
        try:
            results = {}
            for idx, img_data in enumerate(req_body["images_base64"]):
                # Get image name if provided, otherwise use index
                img_name = req_body.get("image_names", {}).get(str(idx), f"image_{idx}")
                
                # Decode base64 string to image
                image_data = base64.b64decode(img_data)
                
                # Save to temp file
                temp_image_path = f"/tmp/temp_image_{idx}.jpg"
                with open(temp_image_path, "wb") as temp_file:
                    temp_file.write(image_data)
                
                # Process the image
                try:
                    img_result = extract_scores_from_image(temp_image_path)
                    results[img_name] = img_result
                except Exception as e:
                    results[img_name] = {"error": str(e)}
                
                # Clean up
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
            
            return func.HttpResponse(
                json.dumps(results),
                status_code=200,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Error processing multiple base64 images: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=500,
                mimetype="application/json"
            )
    
    # If it's a URL to an image
    elif "image_url" in req_body:
        try:
            # Download the image
            response = requests.get(req_body["image_url"])
            response.raise_for_status()
            
            # Save to temp file with correct extension based on content type
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            extension = '.jpg'
            if 'png' in content_type:
                extension = '.png'
            elif 'gif' in content_type:
                extension = '.gif'
                
            temp_image_path = f"/tmp/temp_image{extension}"
            with open(temp_image_path, "wb") as temp_file:
                temp_file.write(response.content)
            
            # Process the image
            result = extract_scores_from_image(temp_image_path)
            
            # Clean up
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                
            return func.HttpResponse(
                json.dumps(result),
                status_code=200,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Error processing image URL: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=500,
                mimetype="application/json"
            )
    
    # If it's multiple URLs to images
    elif "image_urls" in req_body:
        try:
            results = {}
            for idx, url in enumerate(req_body["image_urls"]):
                # Get image name if provided, otherwise use URL or index
                img_name = req_body.get("image_names", {}).get(str(idx), os.path.basename(url) or f"image_{idx}")
                
                try:
                    # Download the image
                    response = requests.get(url)
                    response.raise_for_status()
                    
                    # Save to temp file with correct extension based on content type
                    content_type = response.headers.get('Content-Type', 'image/jpeg')
                    extension = '.jpg'
                    if 'png' in content_type:
                        extension = '.png'
                    elif 'gif' in content_type:
                        extension = '.gif'
                    
                    temp_image_path = f"/tmp/temp_image_{idx}{extension}"
                    with open(temp_image_path, "wb") as temp_file:
                        temp_file.write(response.content)
                    
                    # Process the image
                    img_result = extract_scores_from_image(temp_image_path)
                    results[img_name] = img_result
                    
                    # Clean up
                    if os.path.exists(temp_image_path):
                        os.remove(temp_image_path)
                
                except Exception as e:
                    results[img_name] = {"error": str(e)}
            
            return func.HttpResponse(
                json.dumps(results),
                status_code=200,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Error processing multiple image URLs: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=500,
                mimetype="application/json"
            )
    
    else:
        return func.HttpResponse(
            json.dumps({"error": "Request must contain either 'image_base64', 'images_base64', 'image_url', or 'image_urls'"}),
            status_code=400,
            mimetype="application/json"
        )

# For local testing
if __name__ == "__main__":
    # Example usage
    test_image_path = "path/to/your/scorescreen.jpg"
    result = extract_scores_from_image(test_image_path)
    print(json.dumps(result, indent=2))