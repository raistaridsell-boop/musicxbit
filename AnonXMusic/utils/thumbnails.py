import os
import re
import aiofiles
import aiohttp
import asyncio
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from unidecode import unidecode
from ytSearch import VideosSearch

from AnonXMusic import app
from config import YOUTUBE_IMG_URL

# --- Helper Functions (Updated) ---

def resize_image(max_width, max_height, image):
    """Resizes an image while maintaining aspect ratio, using LANCZOS for high quality."""
    width_ratio = max_width / image.size[0]
    height_ratio = max_height / image.size[1]
    
    # Choose the smaller ratio to ensure the image fits within the bounds
    ratio = min(width_ratio, height_ratio)
    
    new_width = int(ratio * image.size[0])
    new_height = int(ratio * image.size[1])
    
    return image.resize((new_width, new_height), Image.LANCZOS)

def circle_mask(img):
    """Creates a circular mask for an image with an inner border."""
    img = img.convert("RGBA")
    
    # Ensure square base for perfect circle
    size = min(img.size)
    img = img.crop((0, 0, size, size))
    
    # Create mask
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    
    # Apply mask
    output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    
    # Add Stylish Inner Border (instead of thick outer)
    border_draw = ImageDraw.Draw(output)
    border_width = 8
    border_draw.ellipse((border_width, border_width, size - border_width, size - border_width), 
                        outline="white", width=border_width)
    return output

def truncate_text(text, max_len=55):
    """Truncates text and adds ellipsis if it's too long."""
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text

# --- Main Function (Enhanced and Cleaned) ---

async def get_thumb(videoid, user_id):
    cache_path = f"cache/{videoid}_{user_id}.png"
    if os.path.isfile(cache_path):
        return cache_path

    temp_thumb_path = f"cache/thumb{videoid}_temp.png"
    url = f"https://www.youtube.com/watch?v={videoid}"
    
    try:
        # 1. Fetch Video Metadata
        results = VideosSearch(url, limit=1)
        res = await results.next()
        
        if not res or not res["result"]:
            print(f"Error: Could not find results for videoid {videoid}")
            return YOUTUBE_IMG_URL

        result = res["result"][0]
        
        # Safe Metadata Extraction (Handling Potential Nones)
        raw_title = result.get("title", "Unknown Title")
        title = re.sub(r"[^\w\s]+", "", unidecode(raw_title)).title() # Better character handling
        
        duration = result.get("duration", "00:00")
        views_raw = result.get("viewCount", {}).get("short", "0 Views")
        views = re.sub(r"\D", "", views_raw) # Keep only numbers/commas, e.g. "1.2M views" -> "1.2M"
        
        channel = result.get("channel", {}).get("name", "Unknown Channel")
        
        # Choose High-Res Thumbnail
        thumbnail_url = result["thumbnails"][-1]["url"].split("?")[0] # Use last (highest res)

        # 2. Download Media concurrently
        async with aiohttp.ClientSession() as session:
            # Download Thumbnail
            thumb_task = session.get(thumbnail_url)
            
            # Download User Photo
            try:
                sp_path = f"cache/user_{user_id}_temp.jpg"
                found_photo = False
                async for photo in app.get_chat_photos(user_id, 1):
                    await app.download_media(photo.file_id, file_name=sp_path)
                    found_photo = True
                
                if not found_photo:
                     sp_path = "AnonXMusic/assets/default_user.png" # Fallback if no photo
            except Exception as e:
                print(f"User photo error: {e}")
                sp_path = "AnonXMusic/assets/default_user.png" # Fallback

            # Await downloads
            try:
                resp = await thumb_task
                if resp.status == 200:
                    async with aiofiles.open(temp_thumb_path, mode="wb") as f:
                        await f.write(await resp.read())
                else:
                     print(f"Error: Thumbnail download failed ({resp.status})")
                     return YOUTUBE_IMG_URL
            except Exception as e:
                 print(f"Thumbnail download error: {e}")
                 return YOUTUBE_IMG_URL

        # 3. Image Processing (The New Style)
        youtube_img = Image.open(temp_thumb_path)
        base_canvas = resize_image(1280, 720, youtube_img) # Base to start processing

        # --- Background: Gradient Darken + Blur ---
        # Create a radial gradient (dark center, darker edges)
        gradient = Image.new('L', (1280, 720), 0)
        grad_draw = ImageDraw.Draw(gradient)
        grad_draw.ellipse((-300, -300, 1580, 1020), fill=180) # Large center glow
        
        background = base_canvas.filter(ImageFilter.GaussianBlur(18)) # Blur first
        
        # Darken based on gradient
        enhancer = ImageEnhance.Brightness(background)
        background = enhancer.enhance(0.3) # Darken overall
        
        # Composite the gradient to darken edges more naturally
        background = Image.composite(background, Image.new('RGB', background.size, 'black'), gradient)
        
        # --- Layout & Overlays ---
        draw = ImageDraw.Draw(background)
        
        # Asset Loading (Check Paths Carefully!)
        asset_dir = "AnonXMusic/assets"
        font_main_path = f"{asset_dir}/font.ttf"
        font_sub_path = f"{asset_dir}/font2.ttf"
        icon_path = f"{asset_dir}/yt_icon.png" # Optional: add a small yt logo icon

        # Dynamic Font Loading with Fallbacks
        try:
            font_title = ImageFont.truetype(font_main_path, 50)
            font_meta = ImageFont.truetype(font_sub_path, 35)
            font_time = ImageFont.truetype(font_sub_path, 30)
        except (IOError, AttributeError):
            print("Warning: Custom fonts not found. Using defaults.")
            font_title = font_meta = font_time = ImageFont.load_default()

        # --- Element 1: Circular Video Thumb ---
        v_thumb = resize_image(300, 300, circle_mask(youtube_img))
        background.paste(v_thumb, (60, 160), mask=v_thumb)

        # --- Element 2: User Profile Photo ---
        try:
            user_img = Image.open(sp_path)
            u_thumb = resize_image(300, 300, circle_mask(user_img))
            background.paste(u_thumb, (920, 160), mask=u_thumb)
        except Exception:
            print(f"Warning: Could not load user image from {sp_path}")

        # --- Element 3: Main Text Block (Title & Meta) ---
        text_x = 60
        title_y = 500
        meta_y = 570
        
        draw.text((text_x, title_y), truncate_text(title), fill="white", font=font_title)
        draw.text((text_x, meta_y), f"{channel}  •  {views} Views", fill="#E0E0E0", font=font_meta)

        # --- Element 4: Modern Progress Bar ---
        bar_x1, bar_y = 60, 660
        bar_x2 = 1220
        bar_height = 10
        
        # Base Bar (Dark Grey/Transparent)
        draw.rounded_rectangle([(bar_x1, bar_y), (bar_x2, bar_y + bar_height)], 
                               fill="#505050", outline=None, radius=5)
        
        # Active Progress Bar (Vibrant Red)
        progress_end_x = int(bar_x1 + (bar_x2 - bar_x1) * 0.35) # Hardcoded 35% progress example
        draw.rounded_rectangle([(bar_x1, bar_y), (progress_end_x, bar_y + bar_height)], 
                               fill="#FF0000", outline=None, radius=5)
                               
        # Elegant Seeker Dot
        seeker_r = 10
        seeker_center = (progress_end_x, bar_y + bar_height // 2)
        draw.ellipse([(seeker_center[0] - seeker_r, seeker_center[1] - seeker_r), 
                      (seeker_center[0] + seeker_r, seeker_center[1] + seeker_r)], 
                      fill="white", outline="#FF0000", width=2)

        # --- Element 5: Time ---
        time_y = 680
        draw.text((bar_x1, time_y), "01:25", fill="#FFFFFF", font=font_time) # Example currentTime
        draw.text((bar_x2 - 100, time_y), duration, fill="#FFFFFF", font=font_time, align="right")

        # 4. Save and Cleanup
        final_img = background.convert("RGB")
        final_img.save(cache_path, quality=95)
        
        # Cleanup temp files
        if os.path.exists(temp_thumb_path): os.remove(temp_thumb_path)
        if sp_path.endswith("_temp.jpg") and os.path.exists(sp_path): os.remove(sp_path)
            
        return cache_path

    except Exception as e:
        print(f"Critical Generation Error: {e}")
        # Always attempt cleanup on error
        if os.path.exists(temp_thumb_path): os.remove(temp_thumb_path)
        return YOUTUBE_IMG_URL

# --- Setup for Running (If this file is run directly) ---
if __name__ == "__main__":
    # Mocking necessary parts if testing standalone
    class MockApp:
        async def get_chat_photos(self, uid, limit):
            yield type('Obj', (object,), {'file_id': 'mock_file_id'})()
        async def download_media(self, fid, file_name):
            print(f"Mock downloading media {fid} to {file_name}")
            Image.new('RGB', (100,100), 'blue').save(file_name) # Save a tiny blue square

    app = MockApp()
    YOUTUBE_IMG_URL = "https://example.com/fallback.png" # Set your fallback

    # Need an asyncio loop to run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Example video ID and user ID for testing
    video_to_test = "dQw4w9WgXcQ" # Rick Astley - Never Gonna Give You Up
    user_to_test = 123456789
    
    # Create cache dir if it doesn't exist
    if not os.path.exists("cache"): os.makedirs("cache")
    # Ensure assets directory exists with default fonts for standalone test to run.
    if not os.path.exists("AnonXMusic/assets"): os.makedirs("AnonXMusic/assets")

    print(f"Testing thumbnail generation for {video_to_test}...")
    result_path = loop.run_until_complete(get_thumb(video_to_test, user_to_test))
    print(f"Thumbnail saved to: {result_path}")
