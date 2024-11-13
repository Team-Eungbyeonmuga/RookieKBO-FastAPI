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

    chrome_driver_path = "/usr/bin/chromedriver"
    # "/usr/bin/chromedriver"
    # "/opt/homebrew/bin/chromedriver"
    service = Service(executable_path=chrome_driver_path)

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless=new")
    # EC2 우분투 환경에서 동작시키기 위해 사용
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36")
    # EC2에서 IP 차단을 우회하기 위해 사용
    chrome_options.add_argument('--proxy-server=http://101.101.217.36:80')

    url = f"https://www.youtube.com/watch?v={video_id}"
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get(url)

    # print("driver.page_source 시작: ", driver.page_source, "끝")

    try:
        WebDriverWait(driver, 30).until(
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
            if not game_info["homeTeam"]:
                game_info["homeTeam"] = team_name
                game_info["homeScores"] = scores[:-4]
                game_info["homeRHEB"] = scores[-4:]
                game_info["homeScore"] = total_score
            else:
                game_info["awayTeam"] = team_name
                game_info["awayScores"] = scores[:-4]
                game_info["awayRHEB"] = scores[-4:]
                game_info["awayScore"] = total_score

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
                    if not game_info["homeTeam"]:
                        game_info["homeTeam"] = team_name
                    else:
                        game_info["awayTeam"] = team_name
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



##################################################################
# Test용
# 실행 명령어
# Local : uvicorn RookieKBOFastAPI:app --reload
# Dev : uvicorn RookieKBOFastAPI:app --host 0.0.0.0 --port 8000
#
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# import time as t
# from bs4 import BeautifulSoup
# import requests
# from selenium.webdriver.support.ui import Select
# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel, Field
# from typing import Generic, TypeVar, Optional
# from datetime import datetime
# import json
# from typing import List
#
# app = FastAPI()
# T = TypeVar('T')


@app.get("/")
def root():
    return {"message": "Hello World"}


class GameDetail(BaseModel):
    startDateTime: datetime
    awayTeam: str
    homeTeam: str
    gameStatus: str
    awayScores: Optional[List[int]] = None  # List[str]로 변경
    homeScores: Optional[List[int]] = None  # List[str]로 변경
    awayRHEB: Optional[List[int]] = None  # List[str]로 변경
    homeRHEB: Optional[List[int]] = None  # List[str]로 변경
    season: str
    place: str


class GetGameDetailResponse(BaseModel):
    gameDetails: List[GameDetail]


class GetGameDetailRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)


# <Good : post_data 동적 설정 및 할당, 데이터 가져오기>
# 특정 날짜 데이터 가져오기
@app.post("/games/detail")
def getGameDetail(request: GetGameDetailRequest):
    # ChromeDriver 경로 설정
    # Local : chrome_driver_path = "/opt/homebrew/bin/chromedriver"
    # Dev : chrome_driver_path = "/usr/bin/chromedriver"
    chrome_driver_path = "/usr/bin/chromedriver"

    # Chrome 옵션 설정
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless")  # 브라우저 창을 띄우지 않고 실행하려면 추가

    # Selenium 드라이버 시작
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # URL로 이동
    url = 'https://www.koreabaseball.com/Schedule/ScoreBoard.aspx'
    driver.get(url)

    # __VIEWSTATE 값을 추출
    try:
        viewstate_element = driver.find_element(By.ID, "__VIEWSTATE")
        viewstate = viewstate_element.get_attribute("value")

        viewstategenerator_element = driver.find_element(By.ID, "__VIEWSTATEGENERATOR")
        viewstategenerator = viewstategenerator_element.get_attribute("value")

        eventvalidation_element = driver.find_element(By.ID, "__EVENTVALIDATION")
        eventvalidation = eventvalidation_element.get_attribute("value")

    finally:
        # 드라이버 종료
        driver.quit()

    # URL 및 헤더 설정
    url = 'https://www.koreabaseball.com/Schedule/ScoreBoard.aspx'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    year = str(request.year)
    month = str(request.month).zfill(2)
    day = str(request.day).zfill(2)
    searchDate = year + month + day

    # print(searchDate)

    # 네트워크 탭에서 확인한 POST 데이터
    post_data = {
        '__VIEWSTATE': viewstate,
        '__VIEWSTATEGENERATOR': viewstategenerator,
        '__EVENTVALIDATION': eventvalidation,
        'ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchDate': searchDate,
        'ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$btnCalendarSelect': ''
    }

    # POST 요청 보내기
    response = requests.post(url, headers=headers, data=post_data)

    # 제공된 HTML 데이터를 BeautifulSoup으로 파싱
    html_data = response.text

    soup = BeautifulSoup(html_data, 'html.parser')

    # print(soup)

    # 모든 경기를 포함하는 div를 찾아냄
    games = soup.find_all('div', class_='smsScore')

    # log
    # print(games)

    all_game_scores = []

    # 각 경기에 대해 처리
    for idx, game in enumerate(games):
        # print(game)
        # 각 경기의 팀 이름을 추출
        left_team = game.find('p', class_='leftTeam').find('strong', class_='teamT').text
        right_team = game.find('p', class_='rightTeam').find('strong', class_='teamT').text
        placeTime = game.find('p', class_='place').text.split()
        print(placeTime)
        place = placeTime[0]
        time = placeTime[1].split(":")
        print(time)
        hour = time[0]
        minute = time[1]

        game_status = game.find('strong', class_='flag').text
        if game_status == "경기종료":
            game_status = "경기 종료"
        elif game_status == "경기전":
            game_status = "경기 예정"
        elif game_status == "경기중":
            game_status = "경기 중"

        # 이닝별 스코어가 있는 테이블을 찾음
        table = game.find('table', class_='tScore')
        rows = table.find('tbody').find_all('tr')

        gameData = GameDetail(
            startDateTime=datetime(int(year), int(month), int(day), int(hour), int(minute)),
            awayTeam=left_team,
            homeTeam=right_team,
            gameStatus=game_status,
            awayScores=[],
            homeScores=[],
            awayRHEB=[],
            homeRHEB=[],
            season="",
            place=place
        )

        # 각 팀의 이름과 이닝별 점수, R, H, E, B 값을 추출
        for row in rows:
            team_name = row.find('th').text
            # 'class' 속성이 없는 <td> 태그 찾기 (class="point"와 class="hit" 제외)
            tds_without_class = row.find_all('td', class_=False)

            # 해당 <td> 태그의 개수
            MaxNumberOfInnings = len(tds_without_class)
            # print(MaxNumberOfInnings)
            if MaxNumberOfInnings == 12:
                gameData.season = "정규시즌"
            elif MaxNumberOfInnings == 15:
                gameData.season = "포스트시즌"
            else:
                gameData.season = "-"

            # TODO: 정규시즌은 12, 포스트시즌은 15이닝까지 존재.
            innings = [int(td.text) if td.text != "-" else -1 for td in
                       row.find_all('td')[:MaxNumberOfInnings]]  # 이닝별 점수는 1~12열까지
            # R, H, E, B 값 추출
            rheb = [int(td.text) if td.text != "" else -1 for td in row.find_all('td')[-4:]]  # 마지막 4열은 R, H, E, B 값
            # total_score = row.find('td', class_='point').text.strip()  # 팀의 전체 점수 추출

            if team_name == left_team:
                gameData.awayScores = innings
                gameData.awayRHEB = rheb
            elif team_name == right_team:
                gameData.homeScores = innings
                gameData.homeRHEB = rheb

        print(gameData)
        all_game_scores.append(gameData)

    # 콘솔 출력
    # for game in all_game_scores:
    #     print(f"경기 종류 {game['season']}")
    #     print(f"경기 상태: {game['gameStatus']}")
    #     print(f"경기: {game['awayTeam']} {game['awayTotalScore']} vs {game['homeTeam']} {game['homeTotalScore']}")
    #     print(f"  원정 팀 점수: {game['awayTeamScores']}")
    #     print(f"  홈 팀 점수: {game['homeTeamScores']}")
    #     print(f"  원정 팀 RHEB: {game['awayRHEB']}")
    #     print(f"  홈 팀 RHEB: {game['homeRHEB']}")
    #     print("-" * 30)

    # JSON 형식으로 응답
    return GetGameDetailResponse(gameDetails=all_game_scores)


# --------------------------------------

class GameSummary(BaseModel):
    date: str
    time: str
    awayTeam: str
    homeTeam: str
    awayScore: Optional[str] = None  # Optional[str]로 변경
    homeScore: Optional[str] = None  # Optional[str]로 변경
    place: str
    note: str
    season: str


class GetGameSummariesResponse(BaseModel):
    gameSummaries: List[GameSummary]


class GetGameSummariesRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    season: str


# @app.post("/games")
def getGameSummaries(request: GetGameSummariesRequest):
    # ChromeDriver 경로 설정
    # Local : chrome_driver_path = "/opt/homebrew/bin/chromedriver"
    # Dev : chrome_driver_path = "/usr/bin/chromedriver"
    chrome_driver_path = "/usr/bin/chromedriver"

    # Chrome 옵션 설정
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless")  # 브라우저 창을 띄우지 않고 실행하려면 추가

    # Selenium 드라이버 시작
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # URL로 이동
    url = 'https://www.koreabaseball.com/Schedule/Schedule.aspx'
    driver.get(url)

    year = str(request.year)
    month = str(request.month).zfill(2)
    season = ""

    if request.season == "정규시즌":
        season = "0,9,6"
    elif request.season == "포스트시즌":
        season = "3,4,5,7"
    else:
        season = "1"

    # 년도와 월, 시즌 선택
    select_year = Select(driver.find_element("id", "ddlYear"))
    select_year.select_by_value(year)  # 2024년 선택

    select_month = Select(driver.find_element("id", "ddlMonth"))
    select_month.select_by_value(month)  # 10월 선택

    select_series = Select(driver.find_element("id", "ddlSeries"))
    select_series.select_by_value(season)  # 포스트시즌 선택
    # 포스트 시즌 : "3,4,5,7"
    # 정규시즌: "0,9,6"

    # 선택 후 페이지가 로드될 시간을 기다림
    t.sleep(1)

    # 페이지 HTML 소스 가져오기
    html = driver.page_source

    # BeautifulSoup을 이용해 파싱
    soup = BeautifulSoup(html, 'html.parser')

    # 경기 일정을 찾는 코드 (테이블에서 추출)
    table = soup.find('table', {'id': 'tblScheduleList'})
    rows = table.find_all('tr')

    no_data_row = table.find('td', {'colspan': '9', 'style': 'text-align: center;'})
    if no_data_row and "데이터가 없습니다." in no_data_row.text:
        # 데이터가 없을 때 빈 리스트 반환
        return []

    games = []
    current_day = None

    for row in rows[1:]:
        # print(row)
        day_cell = row.find('td', class_='day')
        if day_cell:
            current_day = day_cell.text.strip()

        time_cell = row.find('td', class_='time')
        play_cell = row.find('td', class_='play')
        place_cell = row.find_all('td')[-2].text.strip()
        note_cell = row.find_all('td')[-1].text.strip()

        if play_cell and time_cell:
            teams = play_cell.find_all('span')
            scores = play_cell.find_all('span', class_=['win', 'lose', 'same'])

            if len(scores) == 2:  # win과 lose가 모두 있을 때만 처리
                away_score = scores[0].text.strip()
                home_score = scores[1].text.strip()
            else:
                away_score = None
                home_score = None
            away_team = teams[0].text.strip()
            home_team = teams[-1].text.strip()

            # GameInfo 생성
            game = GameSummary(
                date=current_day,
                time=time_cell.text.strip(),
                awayTeam=away_team,
                homeTeam=home_team,
                awayScore=away_score,
                homeScore=home_score,
                place=place_cell,
                note=note_cell,
                season=request.season
            )
            games.append(game)

    # print(games)

    # 드라이버 종료
    driver.quit()

    return games


# -----------------------------------------------------------------------------

class GetGameSummariesInRegularSeasonResponse(BaseModel):
    gameSummariesInRegularSeason: List[GameSummary]


class GetGameSummariesInRegularSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)


@app.post("/games/regular-season")
def getGameSummariesInRegularSeason(request: GetGameSummariesInRegularSeasonRequest):
    year = request.year
    month = request.month
    season = "정규시즌"  # 정규 시즌

    getGameSummariesRequest = GetGameSummariesRequest(year=year, month=month, season=season)

    games = getGameSummaries(getGameSummariesRequest)

    return GetGameSummariesInRegularSeasonResponse(gameSummariesInRegularSeason=games)


# -----------------------------------------------------------------------------

class GetGameSummariestSeasonResponse(BaseModel):
    gameSummariesInPostSeason: List[GameSummary]


class GetGameSummariesInPostSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)


@app.post("/games/post-season")
def getGameSummariesInPostSeason(request: GetGameSummariesInPostSeasonRequest):
    year = request.year
    month = request.month
    season = "포스트시즌"  # 정규 시즌

    getGamesSummariesRequest = GetGameSummariesRequest(year=year, month=month, season=season)

    games = getGameSummaries(getGamesSummariesRequest)

    return GetGameSummariestSeasonResponse(gameSummariesInPostSeason=games)


# -----------------------------------------------------------------------------

class GetGameSummariesAllSeasonResponse(BaseModel):
    gameSummariesInRegularSeason: List[GameSummary]
    gameSummariesInPostSeason: List[GameSummary]


class GetGameSummariesInAllSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)


@app.post("/games/calendar")
def getGamesInAllSeason(request: GetGameSummariesInAllSeasonRequest):
    year = request.year
    month = request.month

    getGameSummariesInRegularSeasonRequest = GetGameSummariesRequest(year=year, month=month, season="정규시즌")

    gameSummariesInRegularSeason = getGameSummaries(getGameSummariesInRegularSeasonRequest)

    getGameSummariesInPostSeasonRequest = GetGameSummariesRequest(year=year, month=month, season="포스트시즌")

    gameSummariesInPostSeason = getGameSummaries(getGameSummariesInPostSeasonRequest)
    print(GetGameSummariesAllSeasonResponse(gameSummariesInRegularSeason=gameSummariesInRegularSeason,
                                            gameSummariesInPostSeason=gameSummariesInPostSeason))

    return GetGameSummariesAllSeasonResponse(gameSummariesInRegularSeason=gameSummariesInRegularSeason,
                                             gameSummariesInPostSeason=gameSummariesInPostSeason)


# ----------------------------------------------------------------------------------------

class GameSummaryOnCalendar(BaseModel):
    date: str
    homeTeam: str
    awayTeam: str
    homeScore: str
    awayScore: str
    gameStatus: str
    season: str


class GetGameSummariesOnCalendarResponse(BaseModel):
    gameSummariesOnCalendar: List[GameSummaryOnCalendar]


class GetGameSummariesOnCalendarRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    season: str


# @app.post("/games/calendar")
def getGameSummariesOnCalendar(request: GetGameSummariesOnCalendarRequest):
    # ChromeDriver 경로 설정
    # Local : chrome_driver_path = "/opt/homebrew/bin/chromedriver"
    # Dev : chrome_driver_path = "/usr/bin/chromedriver"
    chrome_driver_path = "/usr/bin/chromedriver"

    # Chrome 옵션 설정
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--headless")  # 브라우저 창을 띄우지 않고 실행하려면 추가

    # Selenium 드라이버 시작
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # URL로 이동
    url = 'https://www.koreabaseball.com/Schedule/Schedule.aspx'
    driver.get(url)

    year = str(request.year)
    month = str(request.month).zfill(2)
    season = ""

    if request.season == "정규시즌":
        season = "0,9,6"
    elif request.season == "포스트시즌":
        season = "3,4,5,7"
    else:
        season = "1"

    # 년도와 월, 시즌 선택
    select_year = Select(driver.find_element("id", "ddlYear"))
    select_year.select_by_value(year)  # 2024년 선택

    select_month = Select(driver.find_element("id", "ddlMonth"))
    select_month.select_by_value(month)  # 10월 선택

    select_series = Select(driver.find_element("id", "ddlSeries"))
    select_series.select_by_value(season)  # 포스트시즌 선택
    # 포스트 시즌 : "3,4,5,7"
    # 정규시즌: "0,9,6"

    # 선택 후 페이지가 로드될 시간을 기다림
    t.sleep(1)

    # 페이지 HTML 소스 가져오기
    html = driver.page_source

    # BeautifulSoup을 이용해 파싱
    soup = BeautifulSoup(html, 'html.parser')

    # 경기 일정을 찾는 코드 (테이블에서 추출)
    table = soup.find('table', {'id': 'tblScheduleCal'})
    rows = table.find_all('tr')

    no_data_row = table.find('td', {'colspan': '9', 'style': 'text-align: center;'})
    if no_data_row and "데이터가 없습니다." in no_data_row.text:
        # 데이터가 없을 때 빈 리스트 반환
        return []

    gameSummariesOnCalendar = []
    current_day = None

    for row in rows[1:]:

        # 모든 td 요소를 가져옴 (endGame, todayGame 포함)
        day_cells = row.find_all('td', class_=lambda class_name: class_name in ['endGame', 'todayGame', ''])

        for day_cell in day_cells:
            # 날짜 가져오기
            day_num = day_cell.find('li', class_='dayNum')
            if day_num:
                day_num = day_num.text.strip()
                day_str = day_num.zfill(2)
            current_day = year + month + day_str
            print(current_day)

            # <li> 태그들을 모두 가져오기 (rainCancel 포함)
            game_infos = day_cell.find_all('li')

            # 각 경기 정보를 순회하면서 우천취소와 정상 종료 구분
            for game_info in game_infos:
                # 우천취소된 경기 처리
                if 'rainCancel' in game_info.get('class', []):
                    rain_cancel_info = game_info.text.strip()

                    # ":"로 나눈 후 팀명 추출
                    teams = rain_cancel_info.split(":")
                    if len(teams) == 2:
                        away_team = teams[0].strip()  # 앞의 팀명
                        home_team = teams[1].split("[")[0].strip()  # 뒤의 팀명 (구장 정보 제외)
                        gameSummaryOnCalendar = GameSummaryOnCalendar(
                            date=current_day,
                            homeTeam=home_team,
                            awayTeam=away_team,
                            homeScore="-",
                            awayScore="-",
                            gameStatus="경기 취소",
                            season=request.season
                        )
                        print(gameSummaryOnCalendar)
                        gameSummariesOnCalendar.append(gameSummaryOnCalendar)

                # 정상 경기 처리
                elif game_info.find('b'):
                    # 점수 추출
                    score = game_info.find('b').text
                    scores = score.split(':')
                    awayScore = scores[0].strip()
                    homeScore = scores[-1].strip()
                    # 점수를 제외한 나머지 텍스트 추출
                    game_info_text = game_info.text.replace(score, '').strip()
                    teams = game_info_text.split()
                    away_team = teams[0].strip()  # 첫 번째 팀명
                    home_team = teams[-1].strip()  # 마지막 팀명
                    gameSummaryOnCalendar = GameSummaryOnCalendar(
                        date=current_day,
                        homeTeam=home_team,
                        awayTeam=away_team,
                        homeScore=homeScore,
                        awayScore=awayScore,
                        gameStatus="경기 종료",
                        season=request.season
                    )
                    print(gameSummaryOnCalendar)
                    gameSummariesOnCalendar.append(gameSummaryOnCalendar)
                    # 추가: 점수나 우천취소 없이 팀 이름만 있는 경우 처리
                elif len(game_info.text.split(":")) == 2 and "[" in game_info.text:
                    # 팀명과 경기장 추출
                    teams_info = game_info.text.strip()
                    teams = teams_info.split(":")
                    away_team = teams[0].strip()
                    home_team = teams[1].split("[")[0].strip()
                    gameSummaryOnCalendar = GameSummaryOnCalendar(
                        date=current_day,
                        homeTeam=home_team,
                        awayTeam=away_team,
                        homeScore="-",
                        awayScore="-",
                        gameStatus="경기 예정",
                        season=request.season
                    )
                    print(gameSummaryOnCalendar)
                    gameSummariesOnCalendar.append(gameSummaryOnCalendar)

    # 드라이버 종료
    driver.quit()

    return gameSummariesOnCalendar


# ---------------------------------------------------------------------------------

class GetGameSummariesOnCalendarInAllSeasonResponse(BaseModel):
    gameSummariesOnCalendarInRegularSeason: List[GameSummaryOnCalendar]
    gameSummariesOnCalendarInPostSeason: List[GameSummaryOnCalendar]


class GetGameSummariesOnCalendarInAllSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)


@app.post("/games/calendar/all-season")
def getGameSummariesOnCalendarInAllSeason(request: GetGameSummariesOnCalendarInAllSeasonRequest):
    year = request.year
    month = request.month

    getGameSummariesInRegularSeasonRequest = GetGameSummariesOnCalendarRequest(year=year, month=month, season="정규시즌")

    gameSummariesOnCalendarInRegularSeason = getGameSummariesOnCalendar(getGameSummariesInRegularSeasonRequest)

    getGameSummariesOnCalendarInPostSeasonRequest = GetGameSummariesOnCalendarRequest(year=year, month=month,
                                                                                      season="포스트시즌")

    gameSummariesOnCalendarInPostSeason = getGameSummariesOnCalendar(getGameSummariesOnCalendarInPostSeasonRequest)
    print(GetGameSummariesOnCalendarInAllSeasonResponse(
        gameSummariesOnCalendarInRegularSeason=gameSummariesOnCalendarInRegularSeason,
        gameSummariesOnCalendarInPostSeason=gameSummariesOnCalendarInPostSeason))

    return GetGameSummariesOnCalendarInAllSeasonResponse(
        gameSummariesOnCalendarInRegularSeason=gameSummariesOnCalendarInRegularSeason,
        gameSummariesOnCalendarInPostSeason=gameSummariesOnCalendarInPostSeason)
