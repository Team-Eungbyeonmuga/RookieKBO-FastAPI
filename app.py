from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from youtube_transcript_api import YouTubeTranscriptApi
from bs4 import BeautifulSoup
import re
from datetime import datetime
import requests
from typing import List, Dict


app = FastAPI()

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
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript([lang])
        script = transcript.fetch()

        sentences = []
        for sentence in script:
            entry = {
                "text": sentence['text'].replace('\n', ' '),
                "start": sentence['start']
            }
            sentences.append(entry)

        return TranscriptResponse(video_id=video_id, transcript=sentences)

    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))



# 팀 순위 반환 (3번 api)
@app.get("/rankings", response_model=List[TeamRanking])
def get_rankings():
    url = "https://statiz.sporki.com/"
    rankings = get_team_rankings(url)
    return rankings



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


# 최신 순으로 제목, 날짜, 썸네일 이미지, 비디오 id 반환 1번 함수
def get_video_details() -> list[dict]:

    chrome_driver_path =  '/Users/choseyeon/.wdm/drivers/chromedriver/mac64/130.0.6723.91/chromedriver-mac-arm64/chromedriver'
    # "/opt/homebrew/bin/chromedriver"
    service = Service(executable_path=chrome_driver_path)
    options = Options()
    options.add_argument("--headless")  # 브라우저 창 띄우지 않기

    driver = webdriver.Chrome(service=service, options=options)
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



# 날짜에 해당하는 비디오 ID를 가져오는 4번 함수
def get_video_ids(playlist_url: str, target_date: datetime) -> list[str]:
    chrome_driver_path =  '/Users/choseyeon/.wdm/drivers/chromedriver/mac64/130.0.6723.91/chromedriver-mac-arm64/chromedriver'
    # "/opt/homebrew/bin/chromedriver"

    service = Service(executable_path=chrome_driver_path)
    options = Options()
    options.add_argument("--headless")  # 브라우저 창 띄우지 않기

    driver = webdriver.Chrome(service=service, options=options)
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