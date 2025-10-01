# MultiVibeChat 2

![Multi Vibe Chat Screenshot](https://i.imgur.com/Gi9nMhe.jpeg) <!-- Replace with a real screenshot URL later -->

# Multi AI Chat Desktop Client
A PyQt6-based desktop application for managing and interacting with multiple AI chat services simultaneously in a unified interface.

## Acknowledgments
- Built with PyQt6 and QtWebEngine
- Inspired by the need to compare AI responses efficiently
- Inspired by mol-ai/GodMode 🫡
- Inspired by MultiGPT, ChatHub browser extensions 🤭
- Community contributions welcome

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-green.svg)


## Features

- **Multi-Panel Interface** - Chat with multiple AI services side-by-side
- **Synchronized Prompts** - Send the same prompt to all AIs simultaneously
- **NO APIs NEEDED** - Uses native websites, all possible with free accounts
- **Profile Management** - Create and switch between different user profiles (automatically creates new browser profiles in working directory)
- **Persistent Sessions** - Your login states are preserved between sessions
- **Flexible Layouts** - Toggle between 2x2 grid and 4x1 column layouts
- **Zoom Control** - Ctrl+scroll to adjust text size (website zoom) in each panel
- **OAuth Support** - Handles popup-based authentication flows
- **Developer Tools** - Built-in web inspector (Ctrl+Shift+I)

## Supported AI Services

- ChatGPT (OpenAI)
- Claude (Anthropic)
- Grok (xAI)
- Gemini AI Studio (Google)

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Setup

1. Clone this repository:
```bash
git clone https://github.com/mato200/MultiVibeChat.git
cd MultiVibeChat
```

2. Install required dependencies:
```bash
pip install PyQt6 PyQt6-WebEngine
```

3. Run the application:
```bash
python MVC2.py
```

## Usage

### Basic Operation

1. **First Launch**: The app will open with all four AI services loaded
2. **Login**: Click "Login Mode: OFF" to enable manual login mode, then sign in to each service. I recommend signing in 1st to google's Ai studio
3. **Send Prompts**: Type your prompt in the text box and press `Ctrl+Enter` or click "Send to All"
4. **Compare Responses**: View responses from all AIs simultaneously

### Keyboard Shortcuts

- `Ctrl+Enter` - Send prompt to all AIs
- `Ctrl+Scroll` - Zoom in/out in any panel
- `Alt` (hold) - Show URL bars
- `Ctrl+Shift+I` - Open developer tools (right-click)

### Profile Management

**Creating Profiles:**
1. Type a new profile name in the Profile dropdown
2. Click "Switch / Create"
3. A new window will open with the new profile

**Switching Profiles:**
1. Select an existing profile from the dropdown
2. Click "Switch / Create"

Profiles store separate authentication states, cookies, and settings.

### Login Mode

The "Login Mode" toggle allows manual interaction with websites:
- **OFF** (default): Prompts are automatically sent to all AIs
- **ON**: Disables automatic prompt injection, allowing you to manually interact with login pages
- idk if this is actually true lol, AI made a summary

Use Login Mode when:
- Signing in for the first time
- Handling two-factor authentication
- Dealing with OAuth flows

### Pop-up Authentication

When services use OAuth pop-up windows (like Grok's Google sign-in):
1. Click the sign-in button on the service
2. A pop-up window will appear
3. Complete the authentication (It asked me for 2FA confirm on my phone)
4. The pop-up will auto-close when done

Alternatively, use the "🔐 Sign in with Google" button for a dedicated sign-in window.

## Technical Details

### Browser Compatibility

This application uses QtWebEngine (Chromium-based) and includes:
- Standard Chrome user agent
- Modern HTTP headers (sec-ch-ua, Sec-Fetch-*)
- JavaScript compatibility layers for Chrome APIs
- Popup window handling

### Profile Storage

Profiles are stored in hidden directories:
```
.multi_vibe_chat_profile_default/
.multi_vibe_chat_profile_work/
.multi_vibe_chat_profile_personal/
```

Each profile contains:
- Cookies and session data
- Local storage
- Cache
- IndexedDB data

### Configuration

Last used profile is stored in `.multi_vibe_chat_config.json`

## Troubleshooting

### "This browser is not supported" errors

Some services may show browser compatibility warnings. Try:
1. Enable "Login Mode" and sign in manually
2. Use the dedicated sign-in dialog
3. Update your PyQt6-WebEngine to the latest version

### Sessions not persisting

Ensure the profile directories have write permissions:
```bash
chmod -R 755 .multi_vibe_chat_profile_*
```

### Pop-ups not working

If OAuth popups don't open:
1. Check that JavaScript is enabled (it should be by default)
2. Try using the manual "🔐 Sign in with Google" button
3. Use Login Mode and complete authentication in the main panel

## Development

### Project Structure

```
├── WORKING.py              # Main application file
├── README.md               # This file
└── .multi_vibe_chat_*      # Profile directories (auto-generated)
```

### Code Structure

- `RequestInterceptor` - Adds standard HTTP headers
- `CustomWebEnginePage` - Handles navigation and popups
- `CustomWebEngineView` - Main browser view with zoom support
- `MultiVibeChat` - Main application window and logic

## Privacy & Security

- All data is stored locally on your machine, except for queries you are sending to AI providers, obviously
- No telemetry or tracking
- Sessions are isolated per profile
- Use different profiles for different accounts

**Note:** This application stores credentials locally. Ensure your computer is secure and encrypted.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GPL-3.0 license 


## Disclaimer

This software is provided for educational and personal use. Users are responsible for ensuring their use complies with the terms of service of any third-party AI services they access through this application.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

**Happy AI chatting! 🤖✨**

