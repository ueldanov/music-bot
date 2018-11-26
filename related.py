import requests

class Related:
    def __init__(self, ):
        self.yt_api_key = 'AIzaSyC_Ic2Ch8fiK3yzkl6mRp4WUr0mSDaAUaU'
        self.max_results = 10

    def related_songs(self, yt_id):
        return requests.get(
            'https://www.googleapis.com/youtube/v3/search?part=snippet&relatedToVideoId={}&type=video&key={}'
            '&maxResults={}'.format(yt_id, self.yt_api_key, self.max_results))

    def url_to_first_related(self, yt_id):
        songs = self.related_songs(yt_id).json()
        return 'https://www.youtube.com/watch?v={}'.format(songs['items'][0]['id']['videoId'])
