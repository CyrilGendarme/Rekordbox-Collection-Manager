# User for extracting video links from YouTube HTML content, ease of life but no direct usage in the app

from bs4 import BeautifulSoup
from urllib.parse import urljoin

def extract_video_links(html, base_url="https://www.youtube.com"):
    soup = BeautifulSoup(html, 'html.parser')
    urls = []

    # Find all <a> tags with id="video-title"
    for tag in soup.find_all('a', id='video-title', href=True):
        relative_url = tag['href']
        full_url = urljoin(base_url, relative_url)
        urls.append(full_url)

    return urls


if __name__ == "__main__":
    import sys

    print("Paste your HTML, then press Ctrl+D (Linux/Mac) or Ctrl+Z + Enter (Windows):\n")
    html_content = sys.stdin.read()

    links = extract_video_links(html_content)

    print("\nExtracted video URLs:")
    for link in links:
        print(link)