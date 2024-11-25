#######
# TEST
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time as t
from bs4 import BeautifulSoup
import requests
from selenium.webdriver.support.ui import Select
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional
from datetime import datetime
import json
from typing import List

from youtube_transcript_api import YouTubeTranscriptApi

# app = FastAPI()
T = TypeVar('T')
######

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re
from datetime import datetime
import requests
from typing import List, Dict
import aiohttp
import asyncio
import logging

app = FastAPI()

# requests 라이브러리의 로깅 레벨을 DEBUG로 설정
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)

# 날짜 선택 후 비디오 id 반환할 때 사용하는 데이터 모델 (비디오 id 반환)
class VideoIDsResponse(BaseModel):
    video_ids: list[str]

# 자막 반환할 때 사용하는 데이터 모델 (비디오 id, 자막 반환)
class TranscriptResponse(BaseModel):
    video_id: str
    transcript: list[dict]

# 팀 순위 데이터 모델 
class TeamRanking(BaseModel):
    rank: str
    team: str
    games: str
    wins: str
    draws: str
    losses: str
    win_rate: str
    points_for: str
    points_against: str

# 특정 날짜의 경기정보 데이터 모델
class GameInfo(BaseModel):
    season: str
    startDateTime: str
    place: str
    gameStatus: str
    homeTeam: str
    awayTeam: str
    homeScores: List[str]
    awayScores: List[str]
    homeRHEB: List[str]
    awayRHEB: List[str]
    homeScore: int
    awayScore: int

class GameResponse(BaseModel):
    isAvailable: bool
    games: List[GameInfo]

class RankingsResponse(BaseModel):
    ranks: List[TeamRanking]


# 뉴스 크롤링 데이터 모델
class NewsLink(BaseModel):
    title: str
    imageUrl: str
    publisher: str
    link: str


# 100개 전체구단 하이라이트 영상 디테일 반환 (1번 api)
@app.get("/get_videos")
async def get_videos() -> dict:
    try:
        video_details = get_video_details()  # 여기에 크롤링 함수가 필요
        if not video_details:
            raise HTTPException(status_code=404, detail="No videos found.")
        return {"videos": video_details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# video_id에 해당하는 자막 반환 (2번 api)
@app.get("/transcript/{video_id}", response_model=TranscriptResponse)
async def get_transcript(video_id: str, lang: str = 'ko'):
    try:
        transcript_data = extract_transcript(video_id, lang)

        if not transcript_data:
            raise HTTPException(status_code=404, detail="Transcript not found")

        return TranscriptResponse(video_id=video_id, transcript=transcript_data["transcript"])

    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))



# 팀 순위 반환 (3번 api)
@app.get("/rankings", response_model=RankingsResponse)
def get_rankings():
    url = "https://statiz.sporki.com/"
    rankings = get_team_rankings(url)
    return RankingsResponse(ranks=rankings)



# 특정 날짜에 따른 하이라이트 영상 반환 (4번 api)
@app.get("/videoIds/{target_date}", response_model=VideoIDsResponse)
async def get_video_ids_api(target_date: str):
    try:
        # 입력된 날짜를 datetime 객체로 변환
        target_date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        playlist_url = "https://www.youtube.com/playlist?list=PLuY-NTS_5IpzwH3FfskfFOrnui5O5NlkC"
        
        # 해당 날짜에 맞는 비디오 ID 리스트 반환
        video_ids = get_video_ids(playlist_url, target_date_obj)

        if not video_ids:
            raise HTTPException(status_code=404, detail="해당 날짜에 비디오가 없어요")
        
        return VideoIDsResponse(video_ids=video_ids)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 특정 날짜의 게임 정보를 반환 (5번 api)
@app.get("/games/{date}", response_model=GameResponse)
async def get_game_info(date: str):
    return await scrape_game_info(date)


# 최신 순으로 제목, 날짜, 썸네일 이미지, 비디오 id 반환 1번 함수
def get_video_details() -> list[dict]:

    chrome_driver_path = "/usr/bin/chromedriver"
    # "/opt/homebrew/bin/chromedriver"
    # "/usr/bin/chromedriver"
    service = Service(executable_path=chrome_driver_path)


    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless")  # 브라우저 창을 띄우지 않고 실행하려면 추가

    # options = Options()
    # options.add_argument("--headless")  # 브라우저 창 띄우지 않기

    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get("https://www.youtube.com/playlist?list=PLuY-NTS_5IpzwH3FfskfFOrnui5O5NlkC")

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "video-title"))
        )
    except Exception as e:
        print("페이지 로드 대기 중 오류 발생:", e)
        driver.quit()
        return []

    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')

    video_details = []

    # 모든 영상 링크 가져오기
    for video in soup.select("a#video-title"):
        full_url = "https://www.youtube.com" + video['href']
        title = video.get_text().strip()

        # 날짜 추출 (MM.DD 형식)
        match = re.search(r'(\d{1,2}\.\d{1,2})', title)
        if match:
            video_date_str = match.group(1)
            video_date = datetime.strptime(video_date_str, "%m.%d").replace(year=datetime.now().year)

            # 유튜브 URL에서 video_id 추출
            video_id_match = re.search(r"v=([a-zA-Z0-9_-]+)", full_url)
            video_id = video_id_match.group(1) if video_id_match else None
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else ""

            # 영상 정보를 리스트에 추가
            video_details.append({
                'title': title,
                'date': video_date.strftime("%Y-%m-%d"),
                'thumbnail': thumbnail_url,
                'video_id': video_id  # 비디오 ID 추가
            })

    driver.quit()
    return video_details

# YouTube 자막을 추출하는 2번 함수
def extract_transcript(video_id: str, lang: str = 'ko') -> dict:

    chrome_driver_path = "/opt/homebrew/bin/chromedriver"
    # "/usr/bin/chromedriver"
    # "/opt/homebrew/bin/chromedriver"
    service = Service(executable_path=chrome_driver_path)

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless=new")
    # EC2 우분투 환경에서 동작시키기 위해 사용
    # chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36")
    # EC2에서 IP 차단을 우회하기 위해 사용
    # chrome_options.add_argument('--proxy-server=http://101.101.217.36:80')

    url = f"https://www.youtube.com/watch?v={video_id}"
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get(url)

    # print("driver.page_source 시작: ", driver.page_source, "끝")

    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "meta[property='og:title']"))
        )
    except Exception as e:
        print("페이지 로드 대기 중 오류 발생:", e)
        driver.quit()
        return {}

    # 첫 번째 버튼 클릭: "expand" 버튼
    try:
        expand_button_xpath = '//*[@id="expand"]'

        expand_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, expand_button_xpath))
        )
        expand_button.click()
    except Exception as e:
        print("expand 버튼 클릭 중 오류 발생:", e)
        driver.quit()
        return {}

    # 두 번째 버튼 클릭: "스크립트 표시" 버튼
    try:
        button_xpath = '//*[@id="primary-button"]/ytd-button-renderer/yt-button-shape/button'

        script_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, button_xpath))
        )
        script_button.click()
        print("스크립트 표시 버튼 클릭 완료!")
    except Exception as e:
        print("스크립트 표시 버튼 클릭 중 오류 발생:", e)
        driver.quit()
        return {}

    try:
        segments_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#secondary #segments-container'))
        )
    except Exception as e:
        print("#segments-container 요소 대기 중 오류 발생:", e)
        driver.quit()
        return {}

    segments = segments_container.find_elements(By.CSS_SELECTOR, 'ytd-transcript-segment-renderer')

    transcript = []

    # 자막 출력
    for segment in segments:
        try:
            # 자막 텍스트
            text = segment.find_element(By.CSS_SELECTOR, '.segment-text').text
            # 타임스탬프
            timestamp = segment.find_element(By.CSS_SELECTOR, '.segment-timestamp').text.strip()

            # 타임스탬프를 초 단위로 변환 (예: 0:00 -> 0.00)
            minutes, seconds = map(int, timestamp.split(":"))
            start_time = minutes * 60 + seconds + float(timestamp.split(":")[1])/100

            transcript.append({
                "text": text,
                "start": start_time
            })

        except Exception as e:
            print("자막 항목 추출 중 오류 발생:", e)

    driver.quit()
    return {"transcript": transcript}


# 팀 순위를 가져오는 3번 함수
def get_team_rankings(url: str) -> List[Dict[str, str]]:
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    rankings = []

    # 지정한 선택자를 사용하여 요소를 찾기
    target_div = soup.select_one('body > div.warp > div.container > main > div > div.c_box01 >'
                                 ' div.box_type_boared02 > div:nth-child(2) > div:nth-child(1)')

    # 테이블에서 순위 정보 추출
    if target_div:
        rows = target_div.select('table tbody tr')
        for row in rows:
            # 각 td 요소를 가져와서 리스트로 저장
            cols = row.find_all('td')

            if len(cols) >= 10:
                rank = cols[0].text.strip()
                team = cols[1].find('a').text.strip() if cols[1].find('a') else "팀 없음"
                games = cols[2].text.strip()
                wins = cols[3].text.strip()
                draws = cols[4].text.strip()
                losses = cols[5].text.strip()
                win_rate = cols[7].text.strip()
                points_for = cols[8].text.strip()
                points_against = cols[9].text.strip()

                rankings.append({
                    'rank': rank,
                    'team': team,
                    'games': games,
                    'wins': wins,
                    'draws': draws,
                    'losses': losses,
                    'win_rate': win_rate,
                    'points_for': points_for,
                    'points_against': points_against
                })

    return rankings


# 기본 정보 크롤링 함수 비동기화 (5번 함수)
async def get_game_boxes(date: str):
    url = f"https://statiz.sporki.com/schedule/?m=daily&date={date}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
            game_boxes = soup.select('body > div.warp > div.container > section > div.box_type_boared > div.item_box')
            return game_boxes

# 비동기적으로 summary 페이지를 크롤링하는 함수 (5번 함수)
async def fetch_summary(session, summary_url, game_info):
    async with session.get(summary_url) as response:
        summary_content = await response.text()
        summary_soup = BeautifulSoup(summary_content, 'html.parser')

        score_table = summary_soup.select_one('div.table_type03 tbody')
        rows = score_table.select('tr')

        for row in rows:
            team_name = row.select_one('td a').get_text(strip=True)
            scores = []
            for td in row.select('td .score'):
                if td.contents and isinstance(td.contents[0], str):
                    score_text = td.contents[0].strip()
                    scores.append(score_text if score_text.isdigit() else "-")
                else:
                    scores.append("-")

            total_score = int(scores[-4]) if scores[-4].isdigit() else 0
            if not game_info["awayTeam"]:
                game_info["awayTeam"] = team_name
                game_info["awayScores"] = scores[:-4]
                game_info["awayRHEB"] = scores[-4:]
                game_info["awayScore"] = total_score
            else:
                game_info["homeTeam"] = team_name
                game_info["homeScores"] = scores[:-4]
                game_info["homeRHEB"] = scores[-4:]
                game_info["homeScore"] = total_score

# 특정 경기 일정 크롤링 함수 (5번 함수)
async def scrape_game_info(date: str):
    game_boxes = await get_game_boxes(date)  # 비동기적으로 호출
    is_available = bool(game_boxes)

    # 게임 정보가 없는 경우
    if not is_available:
        return {"isAvailable": False, "games": []}

    async with aiohttp.ClientSession() as session:
        tasks = []
        all_game_info = []

        for game in game_boxes:
            header = game.select_one('.box_head')
            full_date_time = header.get_text(strip=True)

            season = full_date_time[:2]
            date_time = full_date_time.split('(')[0][2:]
            place = full_date_time.split('(')[1].replace(')', '')[:2]
            game_status = full_date_time.split('(')[1].replace(')', '')[2:]

            game_info = {
                "season": season,
                "startDateTime": date_time,
                "place": place,
                "gameStatus": game_status,
                "homeTeam": "",
                "awayTeam": "",
                "homeScores": [],
                "awayScores": [],
                "homeRHEB": [],
                "awayRHEB": [],
                "homeScore": 0,
                "awayScore": 0
            }

            # 경기 취소인 경우
            if game_status == '경기취소':
                rows = game.select('.table_type03 tbody tr')
                for row in rows:
                    team_name = row.select_one('td.align_left').get_text(strip=True)
                    if not game_info["awayTeam"]:
                        game_info["awayTeam"] = team_name
                    else:
                        game_info["homeTeam"] = team_name
                all_game_info.append(game_info)
                continue

            # 경기 종료 시 이닝별 점수 테이블 처리
            if game_status == '경기종료':
                summary_link = game.select_one('.btn_box a[href*="summary"]')
                if summary_link:
                    full_link = "https://statiz.sporki.com" + summary_link['href']
                    tasks.append(fetch_summary(session, full_link, game_info))
                    all_game_info.append(game_info)

        # 비동기적으로 summary 페이지 크롤링
        await asyncio.gather(*tasks)

    # 게임 정보가 있을 때 응답 반환
    return {"isAvailable": True, "games": all_game_info}


# 날짜에 해당하는 비디오 ID를 가져오는 4번 함수
def get_video_ids(playlist_url: str, target_date: datetime) -> list[str]:
    chrome_driver_path = "/usr/bin/chromedriver"
    # "/opt/homebrew/bin/chromedriver"
    # "/usr/bin/chromedriver"

    service = Service(executable_path=chrome_driver_path)


    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless")  # 브라우저 창을 띄우지 않고 실행하려면 추가

    # options = Options()
    # options.add_argument("--headless")  # 브라우저 창 띄우지 않기

    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get(playlist_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "video-title"))
        )
    except Exception as e:
        print("페이지 로드 대기 중 오류 발생:", e)
        driver.quit()
        return []

    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')

    video_ids = []

    # 하이라이트 재생목록 순회
    for video in soup.select("a#video-title"):
        full_url = "https://www.youtube.com" + video['href']
        title = video.get_text().strip()

        match = re.search(r'(\d{1,2}\.\d{1,2})', title)
        if match:
            video_date_str = match.group(1)
            video_date = datetime.strptime(video_date_str, "%m.%d").replace(year=datetime.now().year)

            if video_date.date() == target_date.date():
                # 유튜브 URL에서 video_id를 추출
                video_id = re.search(r"v=([a-zA-Z0-9_-]+)", full_url)
                if video_id:
                    video_ids.append(video_id.group(1))

    driver.quit()
    return video_ids


# 뉴스 URL
NEWS_URL = "https://sporki.com/kbaseball/news?sort=2"


# 뉴스 링크를 가져오는 함수 (최신 7개만 추출)
def get_news_links(news_url: str) -> List[NewsLink]:
    chrome_driver_path = "/usr/bin/chromedriver"

    service = Service(executable_path=chrome_driver_path)

    chrome_driver_path = "/usr/bin/chromedriver"
    # "/opt/homebrew/bin/chromedriver"
    # "/usr/bin/chromedriver"
    service = Service(executable_path=chrome_driver_path)


    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless")  # 브라우저 창을 띄우지 않고 실행하려면 추가

    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get(news_url)


    # 로드될 때까지 대기 (최대 10초)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li[data-v-e96c0546]"))
        )
    except Exception as e:
        print("페이지 로드 대기 중 오류 발생:", e)
        driver.quit()
        return []

    # 페이지 소스 가져오기
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')

    # 뉴스 링크 리스트
    news_links = []

    articles = soup.select("li[data-v-e96c0546]")

    for article in articles[:7]:
        # 이미지 URL 추출
        img_tag = article.select_one(".img img")
        imageUrl = img_tag['src'] if img_tag else "이미지 없음"

        # 제목 추출
        title_tag = article.select_one(".title")
        title = title_tag.text.strip() if title_tag else "제목 없음"

        # 언론사 이름 추출
        publisher_tag = article.select_one(".info-more .name")
        publisher = publisher_tag.text.strip() if publisher_tag else "언론사 없음"

        # 링크 추출
        link_tag = article.find("a")
        link = link_tag['href'] if link_tag else "링크 없음"

        full_link = "https://sporki.com" + link if link != "링크 없음" else link

        # 추출된 정보 추가
        news_links.append({
            'title': title,
            'imageUrl': imageUrl,
            'publisher': publisher,
            'link': full_link
        })

    driver.quit()

    return news_links


@app.post("/news", response_model=List[NewsLink])
async def fetch_news_links():
    return get_news_links(NEWS_URL)


# # video_id에 해당하는 자막 반환 (2번 api)
# @app.get("/transcript/test/{video_id}", response_model=TranscriptResponse)
# async def get_transcript_test(video_id: str, lang: str = 'ko'):
#     try:
#         transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
#         transcript = transcript_list.find_transcript([lang])
#         script = transcript.fetch()
#
#         sentences = []
#         for sentence in script:
#             entry = {
#                 "text": sentence['text'].replace('\n', ' '),
#                 "start": sentence['start']
#             }
#             sentences.append(entry)
#
#         return TranscriptResponse(video_id=video_id, transcript=sentences)
#
#     except Exception as e:
#         raise HTTPException(status_code=404, detail=str(e))

# 프록시 서버 설정 (예시)
# proxy = {
#     "http": "http://101.101.217.36:80"
# }
#
#
# # 프록시가 적용된 세션 설정
# def create_proxied_session():
#     session = requests.Session()
#     session.proxies.update(proxy)
#     return session
#
#
# # YouTubeTranscriptApi를 프록시 세션과 함께 사용하는 함수
# def fetch_transcript_with_proxy(video_id: str, lang: str):
#     session = create_proxied_session()
#
#     # YouTubeTranscriptApi의 요청을 세션을 통해 보내도록 설정
#     YouTubeTranscriptApi._session = session
#     try:
#         transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
#         transcript = transcript_list.find_transcript([lang])
#         script = transcript.fetch()
#
#         return [
#             {
#                 "text": sentence['text'].replace('\n', ' '),
#                 "start": sentence['start']
#             } for sentence in script
#         ]
#     except Exception as e:
#         raise HTTPException(status_code=404, detail=str(e))
#
#
# # API 엔드포인트
# @app.get("/transcript/test/{video_id}", response_model=TranscriptResponse)
# async def get_transcript_test(video_id: str, lang: str = 'ko'):
#     sentences = fetch_transcript_with_proxy(video_id, lang)
#     return TranscriptResponse(video_id=video_id, transcript=sentences)