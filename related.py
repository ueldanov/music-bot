import requests


class Related:
    def __init__(self, ):
        self.yt_api_key = ''
        self.max_results = 10

    def related_songs(self, yt_id):
        return requests.get(
            'https://www.googleapis.com/youtube/v3/search?part=snippet&relatedToVideoId={}&type=video&key={}'
            '&maxResults={}'.format(yt_id, self.yt_api_key, self.max_results))

    def url_to_first_related(self, yt_id, excluded_items=None):
        if excluded_items is None:
            excluded_items = []
        songs = self.related_songs(yt_id).json()
        for item in songs['items']:
            if item['id']['videoId'] not in excluded_items:
                if self.in_music_category(item['id']['videoId']):
                    return 'https://www.youtube.com/watch?v={}'.format(item['id']['videoId'])
        return None

    def in_music_category(self, yt_id):
        result = requests.get(
            'https://www.googleapis.com/youtube/v3/videos?part=snippet&id={}&key={}'.format(yt_id, self.yt_api_key)
        )
        return True
        try:
            if result.json()['items'][0]['snippet']['categoryId'] == '10':
                print(yt_id)
                return True
            else:
                return False
        except ValueError:
            return False
