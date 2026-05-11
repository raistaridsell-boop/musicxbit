import os
import re
import aiofiles
import aiohttp
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from unidecode import unidecode
from ytSearch import VideosSearch

from AnonXMusic import app
from config import YOUTUBE_IMG_URL

def changeImageSize(maxWidth, maxHeight, image):
    widthRatio = maxWidth / image.size[0]
    heightRatio = maxHeight / image.size[1]
    newWidth = int(widthRatio * image.size[0])
    newHeight = int(heightRatio * image.size[1])
    return image.resize((newWidth, newHeight), Image.LANCZOS)

def circle(img):
    img = img.convert("RGBA")
    h, w = img.size
    # Create mask
    mask = Image.new('L', (h, w), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, h, w), fill=255)
    
    # Apply mask
    output = Image.new('RGBA', (h, w), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    
    # Add White Border
    border_draw = ImageDraw.Draw(output)
    border_draw.ellipse((0, 0, h, w), outline="white", width=10)
    return output

def clear(text):
    if len(text) > 50:
        return text[:47] + "..."
    return text

async def get_thumb(videoid, user_id):
    cache_path = f"cache/{videoid}_{user_id}.png"
    if os.path.isfile(cache_path):
        return cache_path

    url = f"https://www.youtube.com/watch?v={videoid}"
    try:
        results = VideosSearch(url, limit=1)
        res = await results.next()
        result = res["result"][0]
        
        title = re.sub("\W+", " ", result.get("title", "Unsupported Title")).title()
        duration = result.get("duration", "00:00")
        views = result.get("viewCount", {}).get("short", "Unknown Views")
        channel = result.get("channel", {}).get("name", "Unknown Channel")
        thumbnail = result["thumbnails"][0]["url"].split("?")[0]

        # Download Thumbnail
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    async with aiofiles.open(f"cache/thumb{videoid}.png", mode="wb") as f:
                        await f.write(await resp.read())

        # Get User Profile Photo
        try:
            sp = f"cache/user_{user_id}.jpg"
            async for photo in app.get_chat_photos(user_id, 1):
                await app.download_media(photo.file_id, file_name=sp)
        except:
            sp = "AnonXMusic/assets/default_user.png" # Fallback image

        # Processing Image
        youtube = Image.open(f"cache/thumb{videoid}.png")
        bg_img = changeImageSize(1280, 720, youtube)
        
        # Background: Blur + Darken
        background = bg_img.filter(ImageFilter.GaussianBlur(15))
        enhancer = ImageEnhance.Brightness(background)
        background = enhancer.enhance(0.4) 

        # Paste Circular Images (Video Thumb & User Profile)
        y = changeImageSize(280, 280, circle(youtube))
        background.paste(y, (80, 150), mask=y)
        
        if os.path.exists(sp):
            user_img = Image.open(sp)
            a = changeImageSize(280, 280, circle(user_img))
            background.paste(a, (920, 150), mask=a)

        draw = ImageDraw.Draw(background)
        
        # Fonts (Check path accuracy)
        font_path = "AnonXMusic/assets/font.ttf"
        bold_font_path = "AnonXMusic/assets/font2.ttf"
        
        font = ImageFont.truetype(font_path, 45) if os.path.exists(font_path) else ImageFont.load_default()
        sub_font = ImageFont.truetype(bold_font_path, 35) if os.path.exists(bold_font_path) else ImageFont.load_default()

        # Text Drawing
        draw.text((80, 480), clear(title), fill="white", font=font)
        draw.text((80, 540), f"{channel}  |  {views}", fill="#CACACA", font=sub_font)
        
        # Progress Bar (Modern Look)
        draw.line([(80, 640), (1200, 640)], fill="grey", width=8)
        draw.line([(80, 640), (450, 640)], fill="#FF0000", width=8) # Red progress
        draw.ellipse([(440, 630), (460, 650)], fill="white")

        # Time
        draw.text((80, 660), "01:25", fill="white", font=sub_font)
        draw.text((1110, 660), duration, fill="white", font=sub_font)

        # Final cleanup and save
        background = background.convert("RGB")
        background.save(cache_path)
        
        if os.path.exists(f"cache/thumb{videoid}.png"):
            os.remove(f"cache/thumb{videoid}.png")
            
        return cache_path

    except Exception as e:
        print(f"Error: {e}")
        return YOUTUBE_IMG_URL
