# Install necessary libraries
!pip install flask pyngrok pandas requests beautifulsoup4

import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, render_template_string
from pyngrok import ngrok
import io
!ngrok authtoken 2oYbW6kwTdXHpKfTvjwZc2S4dLk_gEVftCJPgtRJARcm8f9B
app = Flask(__name__)

# Define social media base URLs to look for
social_platforms = {
    "Facebook": "facebook.com",
    "LinkedIn": "linkedin.com",
    "GitHub": "github.com",
    "Twitter": ["twitter.com", "x.com"]  # Both twitter.com and x.com for Twitter
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.183 Safari/537.36'
}

# Function to extract social media links from a given domain
def extract_social_links(url):
    links = {platform: None for platform in social_platforms.keys()}  # Initialize with None
    try:
        # Fetch the webpage with headers
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # Search for social media links
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]

            # Check if the href contains any social media base URL
            for platform, base_urls in social_platforms.items():
                if isinstance(base_urls, list):  # Multiple URL options (like Twitter)
                    if any(base_url in href for base_url in base_urls) and not links[platform]:
                        links[platform] = href
                elif base_urls in href and not links[platform]:  # Single URL pattern
                    links[platform] = href

    except requests.RequestException as e:
        print(f"Failed to fetch {url}: {e}")

    return links

# Main function to process the DataFrame and add social media links
def run_social_scraping(df):
    results = []

    # Process each domain and find social media links
    for domain in df['domain']:
        # Ensure the URL is properly formatted
        if not domain.startswith('http'):
            domain = "http://" + domain  # Add http if missing

        # Extract social links for each domain
        social_links = extract_social_links(domain)
        social_links["Domain"] = domain
        results.append(social_links)  # Append the dictionary to results list

    # Convert the results to a DataFrame
    results_df = pd.DataFrame(results)
    return results_df

# Route to upload CSV and start scraping
@app.route('/', methods=['GET', 'POST'])
def index():
    # HTML content for the form
    form_html = '''
    <!doctype html>
    <html>
      <head><title>Social Scraper</title></head>
      <body>
        <h2>Upload CSV with Domains to Scrape Social Links</h2>
        <form method="post" enctype="multipart/form-data">
          <label>Upload your CSV file:</label>
          <input type="file" name="file" accept=".csv">
          <button type="submit">Scrape Social Links</button>
        </form>
        {% if error_message %}
          <p style="color: red;">{{ error_message }}</p>
        {% endif %}
      </body>
    </html>
    '''
    if request.method == 'POST':
        try:
            if 'file' not in request.files:
                return render_template_string(form_html, error_message="No file uploaded. Please upload a CSV file.")

            file = request.files['file']
            print("CSV file uploaded.")  # Debugging statement

            # Try to read the CSV file
            try:
                df = pd.read_csv(file)  # Read the uploaded CSV file
                print("CSV file read successfully.")  # Debugging statement
            except Exception as e:
                return render_template_string(form_html, error_message="Invalid file format. Please upload a valid CSV file.")

            if 'domain' not in df.columns:
                return render_template_string(form_html, error_message="Invalid CSV format. The file must contain a 'domain' column.")

            # Run scraping
            output_df = run_social_scraping(df)  # Process the CSV to get social URLs
            print("Scraping completed successfully.")  # Debugging statement

            # Save to CSV for download
            output = io.BytesIO()
            output_df.to_csv(output, index=False)
            output.seek(0)

            print("CSV output generated successfully.")  # Debugging statement
            return send_file(output, as_attachment=True, download_name="social_media_links_output.csv", mimetype='text/csv')
        
        except Exception as e:
            print("Error during file processing:", e)  # Print error to Colab output for debugging
            return render_template_string(form_html, error_message="An unexpected error occurred during processing. Please try again.")

    return render_template_string(form_html)

# Set up ngrok and run the app
public_url = ngrok.connect(5000)
print("Public URL:", public_url)

# Start the Flask app
app.run(port=5000)
