import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, render_template_string
from flask_socketio import SocketIO, emit
import io

# Initialize Flask and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

# Define social media base URLs
social_platforms = {
    "Facebook": "facebook.com",
    "LinkedIn": "linkedin.com",
    "GitHub": "github.com",
    "Twitter": ["twitter.com", "x.com"]
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.183 Safari/537.36'
}

# Function to extract social media links
def extract_social_links(url):
    links = {platform: None for platform in social_platforms.keys()}
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

# Function to handle social media scraping in chunks and emit progress updates
def run_social_scraping(df, chunk_size=10):
    results = []
    total_domains = len(df)
    processed_domains = 0

    for i, domain in enumerate(df['domain']):
        print(f"Processing domain {i + 1}/{total_domains}: {domain}")  # Debugging output
        if not domain.startswith('http'):
            domain = "http://" + domain
        social_links = extract_social_links(domain)
        social_links["Domain"] = domain
        results.append(social_links)

        processed_domains += 1

        # Emit progress every chunk_size domains processed or for the last domain
        if processed_domains % chunk_size == 0 or processed_domains == total_domains:
            print(f"Processed {processed_domains}/{total_domains} domains")  # Debugging output
            socketio.emit('progress', {'processed': processed_domains, 'total': total_domains})  # Emit progress update to client

    return pd.DataFrame(results)

@app.route('/', methods=['GET', 'POST'])
def index():
    form_html = '''
    <!doctype html>
    <html>
      <head>
        <title>Social Scraper</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.min.js"></script>
        <script type="text/javascript" charset="utf-8">
            var socket = io();
            socket.on('progress', function(data) {
                document.getElementById('progress').innerText = "Processed: " + data.processed + " / " + data.total + " domains";
            });
        </script>
      </head>
      <body>
        <h2>Upload CSV with Domains to Scrape Social Links</h2>
        <form method="post" enctype="multipart/form-data">
          <label>Upload your CSV file:</label>
          <input type="file" name="file" accept=".csv">
          <button type="submit">Scrape Social Links</button>
        </form>
        <p id="progress">Processed: 0 / 0 domains</p>
        {% if error_message %}
          <p style="color: red;">{{ error_message }}</p>
        {% endif %}
      </body>
    </html>
    '''

    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template_string(form_html, error_message="No file uploaded. Please upload a CSV file.")

        file = request.files['file']
        try:
            # Read CSV into a DataFrame
            df = pd.read_csv(file)
            chunk_size = 10  # Process the CSV in chunks of 10 rows at a time
            results = pd.DataFrame()

            # Process the entire CSV file and emit progress
            chunk_results = run_social_scraping(df, chunk_size)
            results = pd.concat([results, chunk_results], ignore_index=True)

            # Prepare CSV file for download
            output = io.BytesIO()
            results.to_csv(output, index=False)
            output.seek(0)

            return send_file(output, as_attachment=True, download_name="social_media_links_output.csv", mimetype='text/csv')

        except Exception as e:
            print("Error during file processing:", e)
            return render_template_string(form_html, error_message="An unexpected error occurred during processing. Please try again.")

    return render_template_string(form_html)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
