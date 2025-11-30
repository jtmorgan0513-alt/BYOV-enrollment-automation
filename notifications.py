import io
import os
import zipfile
import mimetypes
import smtplib
import json
import requests
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formatdate
from datetime import datetime

import streamlit as st
import file_storage


def get_sears_html_template(record, include_logo=True):
    """Generate a branded HTML email template with Sears styling."""
    
    industries_list = record.get('industry', record.get('industries', []))
    industries_str = ", ".join(industries_list) if industries_list else "None"
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y at %I:%M %p")
        except Exception:
            pass
    
    logo_section = ""
    if include_logo:
        logo_section = f"""
        <div style="text-align: center; padding: 20px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" width="300" height="90" style="display:block; margin: 0 auto;">
  <!-- Sears text -->
  <text x="20" y="80" font-family="Arial, sans-serif" font-size="72" font-weight="bold" fill="#0066CC">sears</text>
  <!-- Home Services text -->
  <text x="20" y="110" font-family="Arial, sans-serif" font-size="18" font-weight="600" fill="#333333" letter-spacing="4">HOME SERVICES</text>
  <!-- House icon -->
  <circle cx="320" cy="50" r="20" fill="#00CC99"/>
  <path d="M315 50 L320 45 L325 50 L325 60 L315 60 Z" fill="white"/>
</svg>
        </div>
        """
        """
