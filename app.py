import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, render_template_string, jsonify
from flask_socketio import SocketIO, emit
import io

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

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

# Extract social links
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
    except requests.RequestException:
        pass
    return links

# Main function with progress tracking
def run_social_scraping(df):
    results = []
    total_domains = len(df)
    for i, domain in enumerate(df['domain']):
        if not domain.startswith('http'):
            domain = "http://" + domain
        social_links = extract_social_links(domain)
        social_links["Domain"] = domain
        results.append(social_links)
        
        # Emit progress
        socketio.emit('progress', {'percentage': int((i + 1) / total_domains * 100)}, broadcast=True)
    
    return pd.DataFrame(results)

# Frontend and upload handling
@app.route('/', methods=['GET', 'POST'])
def index():
    form_html = '''
    <!doctype html>
    <html>
      <head><title>Social Scraper</title></head>
      <body>
        <h2>Upload CSV with Domains to Scrape Social Links</h2>
        <form id="uploadForm" method="post" enctype="multipart/form-data">
          <label>Upload your CSV file:</label>
          <input type="file" name="file" accept=".csv">
          <button type="submit">Scrape Social Links</button>
        </form>
        <div id="progress">
          <p>Progress: <span id="progressPercent">0%</span></p>
        </div>
        {% if error_message %}
          <p style="color: red;">{{ error_message }}</p>
        {% endif %}

        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
        <script>
          const socket = io();
          socket.on('progress', (data) => {
            document.getElementById('progressPercent').innerText = data.percentage + '%';
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
            except Exception:
                return render_template_string(form_html, error_message="Invalid file format. Please upload a valid CSV file.")

            if 'domain' not in df.columns:
                return render_template_string(form_html, error_message="Invalid CSV format. The file must contain a 'domain' column.")

            output_df = run_social_scraping(df)
            output = io.BytesIO()
            output_df.to_csv(output, index=False)
            output.seek(0)

            return send_file(output, as_attachment=True, download_name="social_media_links_output.csv", mimetype='text/csv')
        
        except Exception as e:
            print("Error during file processing:", e)
            return render_template_string(form_html, error_message="An unexpected error occurred during processing. Please try again.")

    return render_template_string(form_html)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
