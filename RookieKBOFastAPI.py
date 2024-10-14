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

app = FastAPI()
T = TypeVar('T')



@app.get("/")
def root():
    return {"message": "Hello World"}


class MatchDetail(BaseModel):
    year: int
    month: int
    day: int
    awayTeam: str
    homeTeam: str
    gameStatus: str
    awayTeamScores: Optional[List[str]] = None  # List[str]로 변경
    homeTeamScores: Optional[List[str]] = None  # List[str]로 변경
    awayTotalScore: str
    homeTotalScore: str
    awayRHEB: Optional[List[str]] = None  # List[str]로 변경
    homeRHEB: Optional[List[str]] = None  # List[str]로 변경
    season: str
    place: str
    time: str

class GetMatchDetailResponse(BaseModel):
    matchDetails: List[MatchDetail]

class GetMatchDetailRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)


# <Good : post_data 동적 설정 및 할당, 데이터 가져오기>
# 특정 날짜 데이터 가져오기
@app.post("/match-detail")
def getMatchDetail(request: GetMatchDetailRequest):
    # ChromeDriver 경로 설정
    chrome_driver_path = "/opt/homebrew/bin/chromedriver"

    # Chrome 옵션 설정
    chrome_options = Options()
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
        time = placeTime[1]

        game_status = game.find('strong', class_='flag').text
        
        # 이닝별 스코어가 있는 테이블을 찾음
        table = game.find('table', class_='tScore')
        rows = table.find('tbody').find_all('tr')

        gameData = MatchDetail(
                year = year,
                month = month,
                day = day,
                awayTeam = left_team,
                homeTeam = right_team,
                gameStatus = game_status,
                awayTeamScores = [],
                homeTeamScores = [],
                awayTotalScore = "0",
                homeTotalScore = "0",
                awayRHEB = [],
                homeRHEB = [],
                season = "",
                place = place,
                time = time
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
            innings = [td.text for td in row.find_all('td')[:MaxNumberOfInnings]]  # 이닝별 점수는 1~12열까지
            # R, H, E, B 값 추출
            rheb = [td.text for td in row.find_all('td')[-4:]]  # 마지막 4열은 R, H, E, B 값
            total_score = row.find('td', class_='point').text.strip()  # 팀의 전체 점수 추출

            if team_name == left_team:
                gameData.awayTeamScores = innings
                gameData.awayRHEB = rheb
                gameData.awayTotalScore = total_score
            elif team_name == right_team:
                gameData.homeTeamScores = innings
                gameData.homeRHEB = rheb
                gameData.homeTotalScore = total_score

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
    return GetMatchDetailResponse(matchDetails = all_game_scores)

# --------------------------------------

class MatchSummary(BaseModel):
    date: str
    time: str
    awayTeam: str
    homeTeam: str
    awayScore: Optional[str] = None  # Optional[str]로 변경
    homeScore: Optional[str] = None  # Optional[str]로 변경
    place: str
    note: str
    season: str

class GetMatchSummariesResponse(BaseModel):
    matchSummaries: List[MatchSummary]

class GetMatchSummariesRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    season: str
    
# @app.post("/matches")
def getMatchSummaries(request: GetMatchSummariesRequest):
    # # ChromeDriver 경로 설정
    chrome_driver_path = "/opt/homebrew/bin/chromedriver"

    # Chrome 옵션 설정
    chrome_options = Options()
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

    matches = []
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

            # MatchInfo 생성
            match = MatchSummary(
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
            matches.append(match)

    # print(matches)

    # 드라이버 종료
    driver.quit()

    return matches

# -----------------------------------------------------------------------------

class GetMatchSummariesInRegularSeasonResponse(BaseModel):
    matchSummariesInRegularSeason: List[MatchSummary]

class GetMatchSummariesInRegularSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    season: str
    
@app.post("/matches/regular-season")
def getMatchSummariesInRegularSeason(request: GetMatchSummariesInRegularSeasonRequest):

    year = request.year
    month = request.month
    season = "정규시즌"    # 정규 시즌

    getMatchSummariesRequest = GetMatchSummariesRequest(year=year, month=month, season=season)

    matches = getMatchSummaries(getMatchSummariesRequest)

    return GetMatchSummariesInRegularSeasonResponse(matchSummariesInRegularSeason=matches)



# -----------------------------------------------------------------------------

class GetMatchSummariestSeasonResponse(BaseModel):
    matchSummariesInPostSeason: List[MatchSummary]

class GetMatchSummariesInPostSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    
@app.post("/matches/post-season")
def getMatchSummariesInPostSeason(request: GetMatchSummariesInPostSeasonRequest):

    year = request.year
    month = request.month
    season = "포스트시즌"    # 정규 시즌

    getMatchesSummariesRequest = GetMatchSummariesRequest(year=year, month=month, season=season)

    matches = getMatchSummaries(getMatchesSummariesRequest)

    return GetMatchSummariestSeasonResponse(matchSummariesInPostSeason=matches)

# -----------------------------------------------------------------------------

class GetMatchSummariesAllSeasonResponse(BaseModel):
    matchSummariesInRegularSeason: List[MatchSummary]
    matchSummariesInPostSeason: List[MatchSummary]

class GetMatchSummariesInAllSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    
@app.post("/matches/all-season")
def getMatchesInAllSeason(request: GetMatchSummariesInAllSeasonRequest):

    year = request.year
    month = request.month

    getMatchSummariesInRegularSeasonRequest = GetMatchSummariesRequest(year=year, month=month, season="정규시즌")

    matchSummariesInRegularSeason = getMatchSummaries(getMatchSummariesInRegularSeasonRequest)


    getMatchSummariesInPostSeasonRequest = GetMatchSummariesRequest(year=year, month=month, season="포스트시즌")

    matchSummariesInPostSeason = getMatchSummaries(getMatchSummariesInPostSeasonRequest)
    print(GetMatchSummariesAllSeasonResponse(matchSummariesInRegularSeason = matchSummariesInRegularSeason, matchSummariesInPostSeason = matchSummariesInPostSeason))

    return GetMatchSummariesAllSeasonResponse(matchSummariesInRegularSeason = matchSummariesInRegularSeason, matchSummariesInPostSeason = matchSummariesInPostSeason)

# ----------------------------------------------------------------------------------------

class MatchSummaryOnCalendar(BaseModel):
    date: str
    homeTeam: str
    awayTeam: str
    homeScore: str
    awayScore: str
    gameStatus: str
    season: str

class GetMatchSummariesOnCalendarResponse(BaseModel):
    matchSummariesOnCalendar: List[MatchSummaryOnCalendar]

class GetMatchSummariesOnCalendarRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    season: str
    
# @app.post("/matches/calendar")
def getMatchSummariesOnCalendar(request: GetMatchSummariesOnCalendarRequest):
        # # ChromeDriver 경로 설정
    chrome_driver_path = "/opt/homebrew/bin/chromedriver"

    # Chrome 옵션 설정
    chrome_options = Options()
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

    matchSummariesOnCalendar = []
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
                        matchSummaryOnCalendar = MatchSummaryOnCalendar(
                            date = current_day,
                            homeTeam = home_team,
                            awayTeam = away_team,
                            homeScore = "-",
                            awayScore = "-",
                            gameStatus = "경기 취소",
                            season = request.season
                        )
                        print(matchSummaryOnCalendar)
                        matchSummariesOnCalendar.append(matchSummaryOnCalendar)
                
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
                    matchSummaryOnCalendar = MatchSummaryOnCalendar(
                        date = current_day,
                        homeTeam = home_team,
                        awayTeam = away_team,
                        homeScore = homeScore,
                        awayScore = awayScore,
                        gameStatus = "경기 종료",
                        season = request.season
                    )
                    print(matchSummaryOnCalendar)
                    matchSummariesOnCalendar.append(matchSummaryOnCalendar)
                                # 추가: 점수나 우천취소 없이 팀 이름만 있는 경우 처리
                elif len(game_info.text.split(":")) == 2 and "[" in game_info.text:
                    # 팀명과 경기장 추출
                    teams_info = game_info.text.strip()
                    teams = teams_info.split(":")
                    away_team = teams[0].strip()
                    home_team = teams[1].split("[")[0].strip()
                    matchSummaryOnCalendar = MatchSummaryOnCalendar(
                        date=current_day,
                        homeTeam=home_team,
                        awayTeam=away_team,
                        homeScore="-",
                        awayScore="-",
                        gameStatus="경기 예정",
                        season=request.season
                    )
                    print(matchSummaryOnCalendar)
                    matchSummariesOnCalendar.append(matchSummaryOnCalendar)


    # 드라이버 종료
    driver.quit()

    return matchSummariesOnCalendar

# ---------------------------------------------------------------------------------

class GetMatchSummariesOnCalendarInAllSeasonResponse(BaseModel):
    matchSummariesOnCalendarInRegularSeason: List[MatchSummaryOnCalendar]
    matchSummariesOnCalendarInPostSeason: List[MatchSummaryOnCalendar]

class GetMatchSummariesOnCalendarInAllSeasonRequest(BaseModel):
    year: int = Field(ge=2001, le=2024)
    month: int = Field(ge=1, le=12)
    
@app.post("/matches/calendar/all-season")
def getMatchSummariesOnCalendarInAllSeason(request: GetMatchSummariesOnCalendarInAllSeasonRequest):

    year = request.year
    month = request.month

    getMatchSummariesInRegularSeasonRequest = GetMatchSummariesOnCalendarRequest(year=year, month=month, season="정규시즌")

    matchSummariesOnCalendarInRegularSeason = getMatchSummariesOnCalendar(getMatchSummariesInRegularSeasonRequest)


    getMatchSummariesOnCalendarInPostSeasonRequest = GetMatchSummariesOnCalendarRequest(year=year, month=month, season="포스트시즌")

    matchSummariesOnCalendarInPostSeason = getMatchSummariesOnCalendar(getMatchSummariesOnCalendarInPostSeasonRequest)
    print(GetMatchSummariesOnCalendarInAllSeasonResponse(matchSummariesOnCalendarInRegularSeason = matchSummariesOnCalendarInRegularSeason, matchSummariesOnCalendarInPostSeason = matchSummariesOnCalendarInPostSeason))

    return GetMatchSummariesOnCalendarInAllSeasonResponse(matchSummariesOnCalendarInRegularSeason = matchSummariesOnCalendarInRegularSeason, matchSummariesOnCalendarInPostSeason = matchSummariesOnCalendarInPostSeason)