# MultiVibeChat

![Multi Vibe Chat Screenshot](https://i.imgur.com/your-screenshot-url.png) <!-- Replace with a real screenshot URL later -->

A desktop application that provides a unified, tiling interface for prompting multiple AI chat services simultaneously with their native Websites, no APIs needed. Built with Python and PyQt6.

## Features

-   **Multi-AI Tiling:** View and interact with ChatGPT, Claude, Grok, and Google AI Studio in a single 2x2 grid.
-   **Simultaneous Prompting:** Send a single prompt to all AIs at once with a button or a hotkey.
-   **Profile Manager:** UPCOMMING - Easily create and switch between isolated user profiles to manage multiple accounts for each AI service, all from within the app.
-   **Individual Zoom Control:** Zoom in and out of each AI window independently using `Ctrl + Mouse Wheel`.
-   **Send Hotkey:** Use `Ctrl + Enter` in the text box to send your prompt to all services.

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
