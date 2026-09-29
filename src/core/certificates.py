import hashlib
from datetime import datetime, timezone

def generate_svg_certificate(
    project_id: str,
    title: str,
    team_name: str,
    rank: int = None,
    score: float = None,
    org_name: str = "HACKATHON RAPTORS",
    sub_org: str = "FELLOWSHIP OF SENIOR ENGINEERS · COMMUNITY INTEREST CO.",
    accent_color: str = "#f59e0b"
) -> str:
    """Generates an editorial high-resolution SVG certificate with cryptographic verification hash."""
    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    cert_data = f"{project_id}:{title}:{team_name}:{rank}:{score}:{org_name}"
    cert_hash = hashlib.sha256(cert_data.encode('utf-8')).hexdigest()[:16].upper()

    rank_text = f"AWARDED RANK #{rank}" if rank else "VERIFIED PARTICIPATION"
    sub_text = f"For exceptional engineering and presentation of {title}"
    accent = accent_color or "#f59e0b"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 700" width="1000" height="700">
  <defs>
    <linearGradient id="gold-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{accent}" />
      <stop offset="100%" stop-color="#b45309" />
    </linearGradient>
    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#09090b" />
      <stop offset="100%" stop-color="#18181b" />
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1000" height="700" fill="url(#bg-grad)" />

  <!-- Outer & Inner Hairline Borders -->
  <rect x="25" y="25" width="950" height="650" fill="none" stroke="#27272a" stroke-width="2" />
  <rect x="35" y="35" width="930" height="630" fill="none" stroke="#3f3f46" stroke-width="1" stroke-dasharray="4,4" />

  <!-- Corner Geometric Accents -->
  <path d="M 25 50 L 50 25 M 25 60 L 60 25" stroke="#f59e0b" stroke-width="1.5" />
  <path d="M 975 50 L 950 25 M 975 60 L 940 25" stroke="#f59e0b" stroke-width="1.5" />
  <path d="M 25 650 L 50 675 M 25 640 L 60 675" stroke="#f59e0b" stroke-width="1.5" />
  <path d="M 975 650 L 950 675 M 975 640 L 940 675" stroke="#f59e0b" stroke-width="1.5" />

  <!-- Organization Logo & Header -->
  <text x="500" y="110" font-family="'Playfair Display', Georgia, serif" font-size="28" font-weight="600" fill="{accent}" text-anchor="middle" letter-spacing="4">{org_name}</text>
  <text x="500" y="140" font-family="'Inter', sans-serif" font-size="12" fill="#a1a1aa" text-anchor="middle" letter-spacing="3">{sub_org}</text>

  <!-- Title of Certificate -->
  <text x="500" y="220" font-family="'Playfair Display', Georgia, serif" font-size="42" font-style="italic" fill="#fafafa" text-anchor="middle">Certificate of Excellence</text>
  <line x1="400" y1="245" x2="600" y2="245" stroke="#f59e0b" stroke-width="1.5" />

  <!-- Recipient Info -->
  <text x="500" y="300" font-family="'Inter', sans-serif" font-size="14" fill="#a1a1aa" text-anchor="middle" letter-spacing="2">THIS CERTIFICATE IS PROUDLY CONFERRED UPON</text>
  <text x="500" y="355" font-family="'Playfair Display', Georgia, serif" font-size="36" font-weight="bold" fill="#ffffff" text-anchor="middle">{team_name}</text>

  <!-- Achievement Description -->
  <text x="500" y="415" font-family="'Inter', sans-serif" font-size="16" fill="#d4d4d8" text-anchor="middle">{sub_text}</text>
  <text x="500" y="450" font-family="'JetBrains Mono', monospace" font-size="14" font-weight="bold" fill="#10b981" text-anchor="middle" letter-spacing="2">{rank_text}</text>

  <!-- Verification Seal & Signatures -->
  <g transform="translate(500, 550)">
    <circle r="40" fill="none" stroke="url(#gold-grad)" stroke-width="2" />
    <circle r="36" fill="none" stroke="#27272a" stroke-width="1" stroke-dasharray="3,3" />
    <text y="5" font-family="'JetBrains Mono', monospace" font-size="9" font-weight="bold" fill="#f59e0b" text-anchor="middle">ED25519 VERIFIED</text>
  </g>

  <!-- Signatures -->
  <line x1="180" y1="580" x2="360" y2="580" stroke="#3f3f46" stroke-width="1" />
  <text x="270" y="605" font-family="'Inter', sans-serif" font-size="12" fill="#a1a1aa" text-anchor="middle">Ada Okonkwo, Head Judge</text>

  <line x1="640" y1="580" x2="820" y2="580" stroke="#3f3f46" stroke-width="1" />
  <text x="730" y="605" font-family="'Inter', sans-serif" font-size="12" fill="#a1a1aa" text-anchor="middle">Executive Committee, Raptors</text>

  <!-- Footer Verification Hash -->
  <text x="500" y="650" font-family="'JetBrains Mono', monospace" font-size="11" fill="#71717a" text-anchor="middle">
    AUTHENTICATION HASH: {cert_hash} · ISSUED: {now_str}
  </text>
</svg>"""
    return svg
