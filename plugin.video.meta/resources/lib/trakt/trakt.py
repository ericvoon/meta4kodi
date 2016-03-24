# -*- coding: utf-8 -*-
from meta.utils.text import to_utf8
from meta.gui import dialogs
from meta import plugin
from meta.utils.properties import get_property, set_property, clear_property
from meta.navigation.tvshows import tv_add_to_library
from meta.navigation.movies import movies_add_to_library
from settings import *
import requests
import time
from language import get_string as _

CLIENT_ID = "865d182dbc8d400906a5d6efd074a55f3a26658a9eea56f23d82be2d70541567"
CLIENT_SECRET = "a6a99ded7c20a15e8f7806f221c18ed48a6f07ff0f46755efad4a69968f4cd70"


def query_trakt(path):
    headers = {'Content-Type': 'application/json', 'trakt-api-version': '2'}
    api_key = CLIENT_ID
    headers['trakt-api-key'] = api_key
    response = requests.request(
        "GET",
        "https://api-v2launch.trakt.tv/{0}".format(path),
        headers=headers)

    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.json()


def search_trakt(**search_params):
    import urllib
    search_params = dict([(k, to_utf8(v))
                          for k, v in search_params.items() if v])
    return query_trakt("search?{0}".format(urllib.urlencode(search_params)))


def find_trakt_ids(id_type, id, query=None, type=None, year=None):
    response = search_trakt(id_type=id_type, id=id)
    if not response and query:
        response = search_trakt(query=query, type=type, year=year)
        if response and len(response) > 1:
            response = [r for r in response if r[r['type']]['title'] == query]

    if response:
        content = response[0]
        return content[content["type"]]["ids"]

    return {}
            
        

def trakt_get_device_code():
    data = {
        'client_id': CLIENT_ID
    }
    headers = {
        'Content-Type': 'application/json'
    }
    request = requests.post('https://api-v2launch.trakt.tv/oauth/device/code',
                            json=data,
                            headers=headers)
    return request.json()


def trakt_get_device_token(device_codes):
    data = {
        "code": device_codes["device_code"],
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {
        'Content-Type': 'application/json'
    }
    start = time.time()
    interval_start = start
    request = requests.post(
                    'https://api-v2launch.trakt.tv/oauth/device/token',
                    json=data,
                    headers=headers)
    while True:
        if time.time() - start < device_codes["expires_in"]:
            if time.time() - interval_start >= device_codes["interval"]:
                request = requests.post(
                    'https://api-v2launch.trakt.tv/oauth/device/token',
                    json=data,
                    headers=headers)

            if request.status_code == 200:
                return request.json()
            
            if request.status_code == 400:
                continue
            
            if  (request.status_code == 404 or
                 request.status_code == 409 or
                 request.status_code == 410 or
                 request.status_code == 418):
                return false

        else:
            return False


def trakt_refresh_token():
    data = {        
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "grant_type": "refresh_token",
        "refresh_token": plugin.get_setting(SETTING_TRAKT_REFRESH_TOKEN)
    }

    headers = {
        'Content-Type': 'application/json'
    }
    
    request = requests.post(
                    'https://api-v2launch.trakt.tv/oauth/token',
                    json=data,
                    headers=headers)
    
    token = request.json()
    plugin.set_setting(SETTING_TRAKT_ACCESS_TOKEN, token["access_token"])
    plugin.set_setting(SETTING_TRAKT_REFRESH_TOKEN, token["refresh_token"])


@plugin.route('/authenticate_trakt')
def trakt_authenticate():
    code = trakt_get_device_code()
    if dialogs.yesno("Athenticate Trakt","please go to https://trakt.tv/activate and enter the code {0}".format(code["user_code"])):
        token = trakt_get_device_token(code)
        if token is not False:
            plugin.set_setting(SETTING_TRAKT_ACCESS_TOKEN, token["access_token"])
            plugin.set_setting(SETTING_TRAKT_REFRESH_TOKEN, token["refresh_token"])
        else:
            dialogs.ok(_("Authenticate Trakt"), _("Something went wrong/nPlease try again"))


def trakt_get_collection(type):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + plugin.get_setting(SETTING_TRAKT_ACCESS_TOKEN),
        'trakt-api-version': '2',
        'trakt-api-key': CLIENT_ID
    }
    response = requests.request(
        "GET",
        "https://api-v2launch.trakt.tv/sync/collection/{0}".format(type),
        headers=headers)

    if (response.status_code == 401):
        dialogs.ok(_("authenticate trakt"), _("please authenticate with trakt"))
        trakt_authenticate()
        return trakt_get_collection(type)
    else:
        return response.json()


def trakt_get_watchlist(type):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + plugin.get_setting(SETTING_TRAKT_ACCESS_TOKEN),
        'trakt-api-version': '2',
        'trakt-api-key': CLIENT_ID
    }
    response = requests.request(
        "GET",
        "https://api-v2launch.trakt.tv/sync/watchlist/{0}".format(type),
        headers=headers)

    if (response.status_code == 401):
        dialogs.ok(_("authenticate trakt"), _("please authenticate with trakt"))
        trakt_authenticate()
        return trakt_get_watchlist(type)
    else:
        return response.json()


def trakt_get_calendar():
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + plugin.get_setting(SETTING_TRAKT_ACCESS_TOKEN),
        'trakt-api-version': '2',
        'trakt-api-key': CLIENT_ID
    }
    response = requests.request(
        "GET",
        "https://api-v2launch.trakt.tv/calendars/my/shows",
        headers=headers)

    if (response.status_code == 401):
        dialogs.ok(_("authenticate trakt"), _("please authenticate with trakt"))
        trakt_authenticate()
        return trakt_get_calendar(type)
    else:
        return response.json()


@plugin.cached(TTL=CACHE_TTL, cache="trakt")        
def trakt_get_next_episodes():
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + plugin.get_setting(SETTING_TRAKT_ACCESS_TOKEN),
        'trakt-api-version': '2',
        'trakt-api-key': CLIENT_ID
    }
    response = requests.request(
        "GET",
        "https://api-v2launch.trakt.tv/sync/watched/shows?extended=noseasons",
        headers=headers)
    shows = response.json()
    hidden_items = trakt_get_hidden_items("progress_watched")
    items = []
    for item in shows:
        show = item["show"]
        id = show["ids"]["trakt"]
        is_hidden = False

        for hidden_item in hidden_items:
                if show["title"] == hidden_item["show"]["title"]:
                    is_hidden = True
                    break

        if is_hidden == False:
            response = requests.request(
                "GET",
                "https://api-v2launch.trakt.tv/shows/{0}/progress/watched".format(id),
                headers=headers)
            response = response.json()
            if response["next_episode"]:
                next_episode = response["next_episode"]
                next_episode["show"] = show["title"]
                items.append(next_episode)

    return items

@plugin.route('/trakt/trakt_add_all_from_watchlist/<type>')
def trakt_add_all_from_watchlist(type):
    if dialogs.yesno(_("Add All From Collection"), _("Are You Sure?")):
        items = trakt_get_watchlist(type)

        for item in items:
            if type == "shows":
                id = item["show"]["ids"]["tvdb"]
                tv_add_to_library(id)
            else:
                id = item["movie"]["ids"]["imdb"]
                movies_add_to_library(id)


@plugin.route('/trakt/trakt_add_all_from_collection/<type>')
def trakt_add_all_from_collection(type):
    if dialogs.yesno(_("Add All From Collection"), _("Are You Sure?")):
        items = trakt_get_collection(type)

        for item in items:
            if type == "shows":
                id = item["show"]["ids"]["tvdb"]
                tv_add_to_library(id)
            else:
                id = item["movie"]["ids"]["imdb"]
                movies_add_to_library(id)


def trakt_get_hidden_items(type):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + plugin.get_setting(SETTING_TRAKT_ACCESS_TOKEN),
        'trakt-api-version': '2',
        'trakt-api-key': CLIENT_ID
    }
    response = requests.request(
        "GET",
        "https://api-v2launch.trakt.tv/users/hidden/{0}".format(type),
        headers=headers)

    if (response.status_code == 401):
        dialogs.ok(_("authenticate trakt"), _("please authenticate with trakt"))
        trakt_authenticate()
        return trakt_get_hidden_items(type)
    else:
        return response.json()
