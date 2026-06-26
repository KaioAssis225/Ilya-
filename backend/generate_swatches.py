import os
import re
import math
import random
from PIL import Image, ImageDraw, ImageFilter

def slugify(text):
    # Convert to lowercase and slugify names
    text = text.lower()
    text = re.sub(r'[áàâãä]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòôõö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9_]+', '_', text)
    return text.strip('_')

# Define target directory
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "app", "static", "uploads", "optionals"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 29 Opcionais definition
OPTIONALS_SPECS = [
    # Alumínio
    {"category": "aluminio", "color_name": "Natural", "base_color": (224, 224, 224), "type": "metal"},
    {"category": "aluminio", "color_name": "Escovado", "base_color": (200, 200, 200), "type": "metal_brushed"},
    {"category": "aluminio", "color_name": "Preto", "base_color": (40, 40, 40), "type": "metal"},
    
    # Tecido Faixa 1
    {"category": "tecido_faixa_1", "color_name": "Camomila", "base_color": (246, 235, 219), "type": "fabric"},
    {"category": "tecido_faixa_1", "color_name": "Canela", "base_color": (167, 90, 56), "type": "fabric"},
    {"category": "tecido_faixa_1", "color_name": "Areia", "base_color": (225, 212, 192), "type": "fabric"},
    {"category": "tecido_faixa_1", "color_name": "Taupe", "base_color": (122, 109, 99), "type": "fabric"},
    
    # Tecido Faixa 2
    {"category": "tecido_faixa_2", "color_name": "Camomila", "base_color": (246, 235, 219), "type": "fabric"},
    {"category": "tecido_faixa_2", "color_name": "Canela", "base_color": (167, 90, 56), "type": "fabric"},
    {"category": "tecido_faixa_2", "color_name": "Areia", "base_color": (225, 212, 192), "type": "fabric"},
    
    # Corda
    {"category": "corda", "color_name": "Natural", "base_color": (200, 173, 127), "type": "rope"},
    {"category": "corda", "color_name": "Grafite", "base_color": (62, 62, 62), "type": "rope"},
    {"category": "corda", "color_name": "Areia", "base_color": (215, 198, 176), "type": "rope"},
    
    # Madeira Teka
    {"category": "madeira_teka", "color_name": "Pátina", "base_color": (165, 158, 149), "type": "wood"},
    {"category": "madeira_teka", "color_name": "Óleo Natural", "base_color": (192, 124, 61), "type": "wood"},
    {"category": "madeira_teka", "color_name": "Carvão", "base_color": (34, 34, 34), "type": "wood"},
    
    # Madeira Freijó
    {"category": "madeira_freijo", "color_name": "Pátina", "base_color": (176, 166, 155), "type": "wood"},
    {"category": "madeira_freijo", "color_name": "Óleo Natural", "base_color": (184, 134, 85), "type": "wood"},
    {"category": "madeira_freijo", "color_name": "Carvão", "base_color": (42, 42, 42), "type": "wood"},
    
    # Couro Soleta
    {"category": "couro_soleta", "color_name": "Caramelo", "base_color": (157, 85, 40), "type": "leather"},
    {"category": "couro_soleta", "color_name": "Palha", "base_color": (234, 213, 179), "type": "leather"},
    {"category": "couro_soleta", "color_name": "Arara Azul", "base_color": (28, 58, 98), "type": "leather"},
    {"category": "couro_soleta", "color_name": "Preto", "base_color": (26, 26, 26), "type": "leather"},
    {"category": "couro_soleta", "color_name": "Cidreira", "base_color": (122, 138, 115), "type": "leather"},
    
    # Couro Pele
    {"category": "couro_pele", "color_name": "Caramelo", "base_color": (157, 85, 40), "type": "leather"},
    {"category": "couro_pele", "color_name": "Palha", "base_color": (234, 213, 179), "type": "leather"},
    {"category": "couro_pele", "color_name": "Arara Azul", "base_color": (28, 58, 98), "type": "leather"},
    {"category": "couro_pele", "color_name": "Preto", "base_color": (26, 26, 26), "type": "leather"},
    {"category": "couro_pele", "color_name": "Cidreira", "base_color": (122, 138, 115), "type": "leather"},
]

def generate_swatch(spec, width=256, height=256):
    img = Image.new("RGB", (width, height), spec["base_color"])
    draw = ImageDraw.Draw(img)
    random.seed(hash(spec["category"] + spec["color_name"]))
    
    textype = spec["type"]
    base = spec["base_color"]
    
    if textype == "metal":
        # Linear gradient and subtle streaks
        for x in range(width):
            factor = 1.0 - 0.15 * math.sin(x * math.pi / width)
            color = tuple(max(0, min(255, int(c * factor))) for c in base)
            draw.line([(x, 0), (x, height)], fill=color)
        # Streaks
        for _ in range(50):
            y = random.randint(0, height - 1)
            length = random.randint(50, width)
            x_start = random.randint(0, width - length)
            shade = random.randint(-10, 10)
            for x in range(x_start, x_start + length):
                pixel = img.getpixel((x, y))
                new_pixel = tuple(max(0, min(255, c + shade)) for c in pixel)
                img.putpixel((x, y), new_pixel)
                
    elif textype == "metal_brushed":
        # Brushed metal: strong streaks + metal sheen
        for x in range(width):
            factor = 1.0 - 0.25 * math.sin(x * math.pi / width) + 0.1 * math.sin(x * 4 * math.pi / width)
            color = tuple(max(0, min(255, int(c * factor))) for c in base)
            draw.line([(x, 0), (x, height)], fill=color)
        # Strong horizontal brush lines
        for _ in range(300):
            y = random.randint(0, height - 1)
            length = random.randint(10, width)
            x_start = random.randint(0, width - length)
            shade = random.randint(-20, 20)
            for x in range(x_start, x_start + length):
                pixel = img.getpixel((x, y))
                new_pixel = tuple(max(0, min(255, c + shade)) for c in pixel)
                img.putpixel((x, y), new_pixel)
                
    elif textype == "fabric":
        # Cross-hatch linen pattern
        # Draw vertical lines
        for x in range(0, width, 2):
            shade = random.randint(-15, 15)
            for y in range(height):
                pixel = img.getpixel((x, y))
                new_pixel = tuple(max(0, min(255, c + shade)) for c in pixel)
                img.putpixel((x, y), new_pixel)
                # also slightly color adjacent to soften it
                if x + 1 < width and random.random() > 0.5:
                    p2 = img.getpixel((x + 1, y))
                    img.putpixel((x + 1, y), tuple(max(0, min(255, c + int(shade * 0.5))) for c in p2))
        # Draw horizontal lines
        for y in range(0, height, 2):
            shade = random.randint(-15, 15)
            for x in range(width):
                pixel = img.getpixel((x, y))
                new_pixel = tuple(max(0, min(255, c + shade)) for c in pixel)
                img.putpixel((x, y), new_pixel)
                if y + 1 < height and random.random() > 0.5:
                    p2 = img.getpixel((x, y + 1))
                    img.putpixel((x, y + 1), tuple(max(0, min(255, c + int(shade * 0.5))) for c in p2))
                    
    elif textype == "rope":
        # Diagonal braided rope texture
        for x in range(-height, width, 8):
            # Draw diagonal thick ropes
            for offset in range(4):
                shade = -12 if offset == 0 or offset == 3 else 8
                for step in range(height):
                    px = x + step + offset
                    py = step
                    if 0 <= px < width:
                        pixel = img.getpixel((px, py))
                        new_pixel = tuple(max(0, min(255, c + shade)) for c in pixel)
                        img.putpixel((px, py), new_pixel)
        # Add perpendicular fine fibers
        for _ in range(500):
            # short diagonal opposite lines
            px = random.randint(0, width - 10)
            py = random.randint(0, height - 10)
            shade = random.randint(-10, 10)
            for offset in range(5):
                if 0 <= px - offset < width and 0 <= py + offset < height:
                    pixel = img.getpixel((px - offset, py + offset))
                    new_pixel = tuple(max(0, min(255, c + shade)) for c in pixel)
                    img.putpixel((px - offset, py + offset), new_pixel)
                    
    elif textype == "wood":
        # Wood grain lines (sine-wave curves)
        # base grain
        for y in range(height):
            # gentle color variation
            factor = 1.0 + 0.05 * math.sin(y * 0.05)
            color = tuple(max(0, min(255, int(c * factor))) for c in base)
            draw.line([(0, y), (width, y)], fill=color)
            
        # Draw wood veins
        num_veins = 12
        for i in range(num_veins):
            vein_y = random.randint(-50, height + 50)
            vein_color = tuple(max(0, min(255, int(c * 0.85))) for c in base) # darker vein
            points = []
            for x in range(0, width + 10, 10):
                # sine wave offsets to make it look organic
                offset_y = 15 * math.sin(x * 0.015 + i) + 8 * math.sin(x * 0.035 + i * 2)
                points.append((x, vein_y + offset_y))
            
            # draw thick vein
            draw.line(points, fill=vein_color, width=random.randint(1, 3))
            
            # draw secondary softer lines next to it
            sub_vein_color = tuple(max(0, min(255, int(c * 0.92))) for c in base)
            sub_points = [(p[0], p[1] + random.randint(4, 10)) for p in points]
            draw.line(sub_points, fill=sub_vein_color, width=1)
            
        # apply light blur and noise
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        
    elif textype == "leather":
        # Leather grain: noise + cells
        # Create noise
        for x in range(width):
            for y in range(height):
                noise = random.randint(-8, 8)
                pixel = img.getpixel((x, y))
                new_pixel = tuple(max(0, min(255, c + noise)) for c in pixel)
                img.putpixel((x, y), new_pixel)
        
        # Cell grain structures
        for _ in range(800):
            cx = random.randint(0, width - 1)
            cy = random.randint(0, height - 1)
            r = random.randint(2, 5)
            # draw tiny shadow cells
            draw.arc([cx - r, cy - r, cx + r, cy + r], 0, 360, fill=tuple(max(0, int(c * 0.9)) for c in base))
            
    return img

print("Iniciando geracao de texturas de luxo para opcionais...")
for spec in OPTIONALS_SPECS:
    cat_slug = slugify(spec["category"])
    color_slug = slugify(spec["color_name"])
    filename = f"swatch_{cat_slug}_{color_slug}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Generate image
    img = generate_swatch(spec)
    img.save(filepath, "PNG")
    print(f"  Gerado: {filename}")

print("\nTodas as 29 imagens de swatch foram geradas com sucesso em app/static/uploads/optionals/!")
