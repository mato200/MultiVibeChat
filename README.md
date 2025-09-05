# MultiVibeChat

![Multi Vibe Chat Screenshot](https://i.imgur.com/reviWKK.png) <!-- Replace with a real screenshot URL later -->

A desktop application that provides a unified, tiling interface for prompting multiple AI chat services simultaneously with their native Websites, no APIs needed. Built with Python and PyQt6.

## Features

-   **Multi-AI Tiling:** View and interact with ChatGPT, Claude, Grok, and Google AI Studio in a single 2x2 grid.
-   **Simultaneous Prompting:** Send a single prompt to all AIs at once with a button or a hotkey.
-   **Profile Manager:** - Easily create and switch between isolated user profiles to manage multiple accounts for each AI service, all from within the app.
-   **Individual Zoom Control:** Zoom in and out of each AI window independently using `Ctrl + Mouse Wheel`.
-   **Send Hotkey:** Use `Ctrl + Enter` in the text box to send your prompt to all services.
-   Curenntly using existing browser profile to bypass possible anti bot detection (google complaining about "unsafe browser" upon login)

## How to Run

This project is built with Python and PyQt6.

basically, write   python a.py   in command line

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/multi-vibe-chat.git
    cd multi-vibe-chat
    ```

2.  **Install dependencies:**
    It's recommended to use a virtual environment.
    ```bash
    # Create and activate a virtual environment (optional but recommended)
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`

    # Install required packages
    pip install -r requirements.txt
    ```

3.  **Run the application:**
    ```bash
    python a.py
    ```
    The first time you run it, a `default` profile will be created. You can create and switch profiles from the control panel at the bottom.

## How to Use

-   Type your prompt in the text box at the bottom.
-   Click **"Send to All"** or press **`Ctrl + Enter`** to submit.

## HOW TO LOGIN 
Disclaimer: This is an advanced method and carries the risk of corrupting your profiles. The recommended method is to log in manually within the app. P

Prerequisites:
    Close both your main web browser (Chrome/Edge) and the Multi Vibe Chat application completely. This is critical.
    Run Multi Vibe Chat at least once to create the empty .multi_vibe_chat_profile_default folder.

Steps:
    Locate the Source Profile Folder (Your main browser's data):
        Microsoft Edge:
            Windows: C:\Users\YourName\AppData\Local\Microsoft\Edge\User Data\Default
            macOS: ~/Library/Application Support/Microsoft Edge/Default
        Google Chrome:
            Windows: C:\Users\YourName\AppData\Local\Google\Chrome\User Data\Default
            macOS: ~/Library/Application Support/Google/Chrome/Default

    (Note: On Windows, AppData is a hidden folder.)

    Locate the Destination Profile Folder (Your app's data):
        This is the folder named .multi_vibe_chat_profile_default located in your main user/home directory (e.g., C:\Users\YourName\).

    Copy the Key Files:
        Navigate into the Source Folder (e.g., ...\User Data\Default).

        Copy the following files and folders:
            The Cookies file
            The Login Data file
            The entire Local Storage folder
            The entire Session Storage folder
        Paste these items directly into the Destination Folder (.multi_vibe_chat_profile_default), overwriting the empty files that are already there.

    Launch Multi Vibe Chat:
        If the versions were compatible and the files were not locked, you should now be logged in to any services you were already logged into on your main browser.
