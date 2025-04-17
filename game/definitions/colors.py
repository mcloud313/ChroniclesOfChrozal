# game/definitions/colors.py
"""
Defines custom color codes and their ANSI escape sequence mappings.
Inspired by common MUD color code systems.
"""

# \x1b is the ESC character, [ starts the sequence, m ends it.
#0=reset, 1=bold, 4=underline
#30-37 = foreground colors, 40-47 = background colors
# 90-97 bright foreground, 100-107 = bright background

COLOR_MAP = {
    #RESET
    "{x": "\x1b[0m",    # Reset all attributes

    # Basic Foreground Colors (Non-bold)
    "{k": "\x1b[0;30m", # Black
    "{R": "\x1b[0;31m", # Red
    "{G": "\x1b[0;32m", # Green
    "{Y": "\x1b[0;33m", # Yellow
    "{B": "\x1b[0;34m", # Blue
    "{M": "\x1b[0;35m", # Magenta
    "{C": "\x1b[0;36m", # Cyan
    "{W": "\x1b[0;37m", # White (often grey)

    # Bright/Bold Foreground Colors (Use these more often for visibility)
    "{K": "\x1b[1;30m", # Bold Black (Dark Grey)
    "{r": "\x1b[1;31m", # Bold Red (Bright Red)
    "{g": "\x1b[1;32m", # Bold Green (Bright Green)
    "{y": "\x1b[1;33m", # Bold Yellow (often Brown/Orange on some clients)
    "{b": "\x1b[1;34m", # Bold Blue (Bright Blue)
    "{m": "\x1b[1;35m", # Bold Magenta (Bright Magenta/Pink)
    "{c": "\x1b[1;36m", # Bold Cyan (Bright Cyan)
    "{w": "\x1b[1;37m", # Bold White (Bright White)

    # Basic Background Colors (Use sparingly)
    "{bk": "\x1b[40m", # Black background
    "{bR": "\x1b[41m", # Red background
    "{bG": "\x1b[42m", # Green background
    "{bY": "\x1b[43m", # Yellow background
    "{bB": "\x1b[44m", # Blue background
    "{bM": "\x1b[45m", # Magenta background
    "{bC": "\x1b[46m", # Cyan background
    "{bW": "\x1b[47m", # White background

    # Add other codes as needed (e.g., underline "{u", blink "{f")
}

# You can add more complex codes like specific RGB later if needed,
# but stick to basic ANSI for broad compatibility.