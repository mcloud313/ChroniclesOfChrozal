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
    # RESET
    "<x>": "\x1b[0m",

    # Basic Foreground Colors
    "<k>": "\x1b[0;30m",  # Black
    "<R>": "\x1b[0;31m",  # Red
    "<G>": "\x1b[0;32m",  # Green
    "<Y>": "\x1b[0;33m",  # Yellow
    "<B>": "\x1b[0;34m",  # Blue
    "<M>": "\x1b[0;35m",  # Magenta
    "<C>": "\x1b[0;36m",  # Cyan
    "<W>": "\x1b[0;37m",  # White

    # Bright/Bold Foreground Colors
    "<K>": "\x1b[1;30m",  # Dark Grey
    "<r>": "\x1b[1;31m",  # Bright Red
    "<g>": "\x1b[1;32m",  # Bright Green
    "<y>": "\x1b[1;33m",  # Yellow/Brown
    "<b>": "\x1b[1;34m",  # Bright Blue
    "<m>": "\x1b[1;35m",  # Bright Magenta
    "<c>": "\x1b[1;36m",  # Bright Cyan
    "<w>": "\x1b[1;37m",  # Bright White

    # Background Colors
    "<bk>": "\x1b[40m",
    "<bR>": "\x1b[41m",
    "<bG>": "\x1b[42m",
    "<bY>": "\x1b[43m",
    "<bB>": "\x1b[44m",
    "<bM>": "\x1b[45m",
    "<bC>": "\x1b[46m",
    "<bW>": "\x1b[47m",
    
    # Special formatting
    "<i>": "\x1b[3m",    # Italic
    "<u>": "\x1b[4m",    # Underline
}

# You can add more complex codes like specific RGB later if needed,
# but stick to basic ANSI for broad compatibility.