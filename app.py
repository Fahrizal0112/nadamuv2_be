from flask import Flask, jsonify, request
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import re
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

def extract_video_id(youtube_url):
    """
    Extract video ID from YouTube URL
    """
    if not youtube_url:
        return None
    
    # Handle different YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
        r'youtube\.com/watch\?.*v=([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, youtube_url)
        if match:
            return match.group(1)
    
    return None

def get_youtube_transcript(video_id, languages=['id', 'en']):
    """
    Get transcript from YouTube video
    """
    try:
        # Try to get transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to find transcript in preferred languages
        transcript = None
        for lang in languages:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except:
                continue
        
        # If no transcript found in preferred languages, get any available
        if not transcript:
            transcript = transcript_list.find_transcript(['en'])  # fallback to English
        
        # Fetch the actual transcript
        fetched_transcript = transcript.fetch()
        
        # Extract snippets from FetchedTranscript object
        if hasattr(fetched_transcript, 'snippets'):
            # New API version - use snippets attribute
            transcript_data = [{
                'text': snippet.text,
                'start': snippet.start,
                'duration': snippet.duration
            } for snippet in fetched_transcript.snippets]
        else:
            # Fallback for older versions
            transcript_data = fetched_transcript
        
        # Format transcript as a single text
        full_text = ' '.join([item['text'] for item in transcript_data])
        
        return {
            'success': True,
            'transcript': full_text,
            'language': transcript.language,
            'language_code': transcript.language_code,
            'is_generated': transcript.is_generated,
            'raw_data': transcript_data
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'transcript': None
        }

@app.route('/api/chapters/transcript', methods=['GET'])
def get_chapters_with_transcript():
    """
    Fetch chapters from external API and add YouTube transcripts
    """
    try:
        # Fetch data from external API
        response = requests.get('https://nadamu.vpsalfach.my.id/api/chapters/')
        response.raise_for_status()
        
        chapters_data = response.json()
        
        if not chapters_data.get('success'):
            return jsonify({
                'success': False,
                'error': 'Failed to fetch chapters data'
            }), 400
        
        # Process each chapter
        for chapter in chapters_data['data']:
            video_url = chapter.get('videoUrl')
            
            if video_url:
                # Extract video ID
                video_id = extract_video_id(video_url)
                
                if video_id:
                    # Get transcript
                    transcript_result = get_youtube_transcript(video_id)
                    
                    # Update chapter data
                    chapter['transcript'] = transcript_result.get('transcript')
                    chapter['transcriptFetched'] = transcript_result.get('success', False)
                    chapter['transcriptInfo'] = {
                        'language': transcript_result.get('language'),
                        'language_code': transcript_result.get('language_code'),
                        'is_generated': transcript_result.get('is_generated'),
                        'error': transcript_result.get('error')
                    }
                else:
                    chapter['transcript'] = None
                    chapter['transcriptFetched'] = False
                    chapter['transcriptInfo'] = {'error': 'Invalid YouTube URL'}
            else:
                chapter['transcript'] = None
                chapter['transcriptFetched'] = False
                chapter['transcriptInfo'] = {'error': 'No video URL provided'}
        
        return jsonify(chapters_data)
        
    except requests.RequestException as e:
        return jsonify({
            'success': False,
            'error': f'Failed to fetch chapters: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/transcript/<video_id>', methods=['GET'])
def get_single_transcript(video_id):
    """
    Get transcript for a single YouTube video
    """
    languages = request.args.getlist('lang') or ['id', 'en']
    
    result = get_youtube_transcript(video_id, languages)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/transcript/url', methods=['POST'])
def get_transcript_from_url():
    """
    Get transcript from YouTube URL
    """
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({
            'success': False,
            'error': 'YouTube URL is required'
        }), 400
    
    video_id = extract_video_id(data['url'])
    
    if not video_id:
        return jsonify({
            'success': False,
            'error': 'Invalid YouTube URL'
        }), 400
    
    languages = data.get('languages', ['id', 'en'])
    result = get_youtube_transcript(video_id, languages)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'YouTube Transcript API is running'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4000)