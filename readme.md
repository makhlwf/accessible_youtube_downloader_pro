# accessible_youtube_downloader_pro
an accessible youtube browser and downloader desktop application designed for nvda screan reader users
# contributers
* Sulaiman Al Qusaimi, Oman
* Abdullah Zain Aldeen: Moroco
* Mustafa Elçiçek, Turkia

# Building from source

To build the application from source, you will need Python 3.9 or newer and `pip`.

## Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/accessible_youtube_downloader_pro.git
    cd accessible_youtube_downloader_pro
    ```

2.  **Install dependencies:**
    It is recommended to use a virtual environment.
    ```bash
    python -m venv venv
    venv\Scripts\activate  # On Windows
    ```
    Then, install the required packages:
    ```bash
    pip install -r requirements.txt
    pip install pyinstaller
    ```

3.  **Run the build script:**
    ```bash
    python build.py
    ```

4.  **Find the executable:**
    The built executable will be located in the `dist` directory.

## Building with GitHub Actions

You can also build the application by using the provided GitHub Actions workflow.
1.  Go to the "Actions" tab of the repository on GitHub.
2.  Under "Workflows", select "Build Application".
3.  Click on "Run workflow", and then "Run workflow" again.
4.  Once the build is complete, you can download the executable from the "Artifacts" section of the workflow run.