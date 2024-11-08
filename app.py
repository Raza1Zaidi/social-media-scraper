pip install celery redis
import os
import pandas as pd
import io
from flask import Flask, request, send_file, render_template_string
from bs4 import BeautifulSoup
import requests
from celery import Celery
import time

app = Flask(__name__)

# Configure Celery
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'  # Redis as message broker
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'  # Redis as result backend
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

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

def run_social_scraping(df, start_index=0, end_index=None):
    results = []
    for domain in df['domain'][start_index:end_index]:
        if not domain.startswith('http'):
            domain = "http://" + domain
        social_links = extract_social_links(domain)
        social_links["Domain"] = domain
        results.append(social_links)

    results_df = pd.DataFrame(results)
    return results_df

# Celery task to process the CSV
@celery.task(bind=True)
def process_csv_task(self, file_path):
    try:
        df = pd.read_csv(file_path)
        total_domains = len(df)
        chunk_size = 100  # Process 100 domains at a time to optimize memory usage
        all_results = []

        # Process in chunks
        for i in range(0, total_domains, chunk_size):
            end_index = min(i + chunk_size, total_domains)
            chunk_df = df[i:end_index]
            result = run_social_scraping(chunk_df, i, end_index)
            all_results.append(result)
            self.update_state(state='PROGRESS', meta={'current': i + chunk_size, 'total': total_domains})
        
        # Concatenate all results
        final_df = pd.concat(all_results, ignore_index=True)
        final_file_path = "output/social_media_links_output.csv"
        final_df.to_csv(final_file_path, index=False)
        return final_file_path
    except Exception as e:
        print(f"Error in processing CSV: {e}")
        raise self.retry(exc=e)

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
        {% if error_message %}
          <p style="color: red;">{{ error_message }}</p>
        {% endif %}
        {% if message %}
          <p>{{ message }}</p>
        {% endif %}
        {% if task_id %}
          <p>Task ID: {{ task_id }}</p>
          <a href="/status/{{ task_id }}">Check Progress</a>
        {% endif %}
      </body>
    </html>
    '''

    if request.method == 'POST':
        try:
            if 'file' not in request.files:
                return render_template_string(form_html, error_message="No file uploaded. Please upload a CSV file.")

            file = request.files['file']
            if not file.filename.endswith('.csv'):
                return render_template_string(form_html, error_message="Invalid file type. Please upload a CSV file.")

            file_path = os.path.join('uploads', file.filename)
            file.save(file_path)

            task = process_csv_task.apply_async(args=[file_path])

            return render_template_string(form_html, task_id=task.id)

        except Exception as e:
            print("Error during file processing:", e)
            return render_template_string(form_html, error_message="An unexpected error occurred during processing. Please try again.")

    return render_template_string(form_html)

@app.route('/status/<task_id>')
def task_status(task_id):
    task = process_csv_task.AsyncResult(task_id)
    if task.state == 'PROGRESS':
        return f"Processing: {task.info['current']} of {task.info['total']} domains."
    elif task.state == 'SUCCESS':
        return send_file(task.result, as_attachment=True)
    elif task.state == 'FAILURE':
        return f"Task failed: {task.info}"
    return "Task not started yet."

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
