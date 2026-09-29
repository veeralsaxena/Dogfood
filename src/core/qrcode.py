import io
import urllib.parse
from typing import Optional
import qrcode
import qrcode.image.svg

def generate_offline_svg_qr(data: str, box_size: int = 8, border: int = 2) -> str:
    """
    Generates a pure vector SVG QR code without any external network, CDN, or image service.
    100% air-gap and offline compliant.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(attrib={"class": "qr-code-svg", "style": "width: 100%; height: auto; max-width: 220px;"})
    
    stream = io.BytesIO()
    img.save(stream)
    return stream.getvalue().decode("utf-8")

def generate_qr_data_uri(data: str) -> str:
    """Returns SVG Data URI suitable for <img src="..."> tags."""
    svg_text = generate_offline_svg_qr(data)
    encoded = urllib.parse.quote(svg_text)
    return f"data:image/svg+xml;utf8,{encoded}"
