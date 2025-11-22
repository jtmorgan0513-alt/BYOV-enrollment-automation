Deployment instructions

Recommended quick steps to deploy the BYOV Streamlit app.

1) Streamlit Community Cloud
- Push this repository to GitHub.
- Add the repo to Streamlit Community Cloud (https://streamlit.io/cloud).
- Add sensitive values in the Streamlit "Secrets" section (see `secrets.toml` example below).
- The app entry point is `byov_app.py`; Streamlit will run it with `streamlit run byov_app.py`.

2) Heroku (or other PaaS)
- Make sure `requirements.txt` is up-to-date.
- Include a `Procfile` with the following content:

  web: streamlit run byov_app.py --server.port $PORT --server.address 0.0.0.0

- Push to Heroku; the Procfile will instruct the dyno to run Streamlit.

Secrets and credentials
- Do NOT commit real credentials into the repository. Use platform secret managers (Streamlit secrets, Heroku config vars, GitHub Actions secrets, etc.).
- Example `secrets.toml` (DO NOT COMMIT real values):

  [email]
  sender = "you@example.com"
  app_password = "your-app-password"
  recipient = "recipient@example.com"

Files and artifacts
- Uploaded files and generated PDFs are stored in `uploads/` and `pdfs/`. These are ignored by `.gitignore` to avoid committing user data.

Local run
- To run locally:

  ```bash
  python -m venv .venv
  source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
  pip install -r requirements.txt
  streamlit run byov_app.py
  ```
