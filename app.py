import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, render_template_string, jsonify
from flask_socketio import SocketIO
import io
import time

# Initialize Flask and SocketIO
app = Flask(__name__)
socketio = SocketIO(app)

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
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            for platform, base_urls in social_platforms.items():
                if isinstance(base_urls, list):
                    if any(base_url in href for base_url in base_urls) and not links[platform]:
                        links[platform] = href
                elif base_urls in href and not links[platform]:
                    links[platform] = href

    except requests.RequestException as e:
        print(f"Failed to fetch {url}: {e}")

    return links

# Main scraping function with progress updates
def run_social_scraping(df):
    results = []
    total_domains = len(df)

    for i, domain in enumerate(df['domain']):
        if not domain.startswith('http'):
            domain = "http://" + domain
        social_links = extract_social_links(domain)
        social_links["Domain"] = domain
        results.append(social_links)

        # Emit progress every 10 domains processed to avoid excessive updates
        if (i + 1) % 10 == 0 or (i + 1) == total_domains:
            socketio.emit('progress', {'percentage': int((i + 1) / total_domains * 100)}, broadcast=True)

        # Delay between requests to manage load
        time.sleep(0.1)

    results_df = pd.DataFrame(results)
    return results_df

# HTML form and progress bar in the front end
@app.route('/', methods=['GET', 'POST'])
def index():
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
        <div id="progress-container" style="display: none;">
          <p>Processing... <span id="progress-text">0%</span></p>
          <progress id="progress-bar" value="0" max="100"></progress>
        </div>
        {% if error_message %}
          <p style="color: red;">{{ error_message }}</p>
        {% endif %}
        <script src="//cdnjs.cloudflare.com/ajax/libs/socket.io/3.1.3/socket.io.min.js"></script>
        <script>
          const socket = io();
          const progressContainer = document.getElementById("progress-container");
          const progressBar = document.getElementById("progress-bar");
          const progressText = document.getElementById("progress-text");

          socket.on('progress', (data) => {
              progressContainer.style.display = "block";
              progressBar.value = data.percentage;
              progressText.textContent = data.percentage + "%";
          });
        </script>
      </body>
    </html>
    '''
    if request.method == 'POST':
        try:
            if 'file' not in request.files:
                return render_template_string(form_html, error_message="No file uploaded. Please upload a CSV file.")

            file = request.files['file']
            try:
                df = pd.read_csv(file)
            except Exception as e:
                return render_template_string(form_html, error_message="Invalid file format. Please upload a valid CSV file.")

            if 'domain' not in df.columns:
                return render_template_string(form_html, error_message="Invalid CSV format. The file must contain a 'domain' column.")

            # Run the social scraping with progress updates
            output_df = run_social_scraping(df)

            output = io.BytesIO()
            output_df.to_csv(output, index=False)
            output.seek(0)

            return send_file(output, as_attachment=True, download_name="social_media_links_output.csv", mimetype='text/csv')
        
        except Exception as e:
            print("Error during file processing:", e)
            return render_template_string(form_html, error_message="An unexpected error occurred during processing. Please try again.")

    return render_template_string(form_html)

# Run the Flask app with SocketIO
if __name__ == '__main__':
    port = 5000  # Default port
    socketio.run(app, host='0.0.0.0', port=port)
