#!/usr/bin/env python3
"""
CSO 주간 뉴스 자동 수집 및 Claude AI 요약 생성
사용: python3 generate_weekly_news.py [WEEK_NUMBER]
"""
import sys
import os
import json
import urllib.request
import urllib.parse
import urllib.error
import datetime
import email.utils
import re
import xml.etree.ElementTree as ET


def get_week_info(week_override=None):
    today = datetime.date.today()
    year, week, _ = today.isocalendar()
    month = today.month
    if week_override:
        week = int(week_override)
    return str(year), str(week), str(month)


def is_recent(pub_date_str, days=30):
    """RSS pubDate가 최근 N일 이내인지 확인 (RFC 2822 형식)."""
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        now = datetime.datetime.now(datetime.timezone.utc)
        return dt >= now - datetime.timedelta(days=days)
    except Exception:
        return True  # 파싱 실패 시 포함


def fetch_google_news_rss(query, max_items=20):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            root = ET.fromstring(resp.read())
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            description = re.sub(r'<[^>]+>', '', item.findtext("description", ""))
            source_el = item.find("source")
            source = source_el.text if source_el is not None else ""
            if title and link and is_recent(pub_date, days=30):
                items.append({
                    "title": title,
                    "url": link,
                    "date": pub_date,
                    "source": source,
                    "description": description[:300]
                })
        return items
    except Exception as e:
        print(f"  ⚠️ RSS 수집 오류 ({query}): {e}")
        return []


def check_url_accessible(url, timeout=8):
    """URL이 실제로 접근 가능한지 확인."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except Exception:
        return False


def validate_and_clean_news(data, year, month):
    """생성된 JSON 품질 검증 및 정제.

    날짜 형식, 필수 필드, 중복, URL 접근성을 검사합니다.
    """
    news = data.get("news", [])
    print(f"  🔍 품질 검증 중... ({len(news)}건)")

    seen_titles = set()
    valid_items = []

    for i, item in enumerate(news):
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        source = item.get("source", "").strip()
        summary = item.get("summary", "").strip()
        date = item.get("date", "").strip()

        issues = []

        # 필수 필드 확인
        if not title:
            issues.append("제목 누락")
        if not url:
            issues.append("URL 누락")
        if not source:
            issues.append("출처 누락")
        if not summary:
            issues.append("요약 누락")
        if issues:
            print(f"    ⚠️  항목 {i+1} 필수 필드 오류: {', '.join(issues)} — 제외")
            continue

        # 중복 제목
        if title in seen_titles:
            print(f"    ⚠️  항목 {i+1} 중복 제목: {title[:40]}... — 제외")
            continue
        seen_titles.add(title)

        # 날짜 형식 정규화 (YYYY.MM.DD 또는 YYYY.MM 허용)
        if not re.match(r'\d{4}\.\d{1,2}', date):
            corrected = f"{year}.{int(month):02d}"
            print(f"    ℹ️  항목 {i+1} 날짜 교정: '{date}' → '{corrected}'")
            item["date"] = corrected

        # URL 접근성 확인
        if not check_url_accessible(url):
            print(f"    ⚠️  항목 {i+1} URL 접근 불가: {url[:60]} — 제외")
            continue

        valid_items.append(item)

    removed = len(news) - len(valid_items)
    if removed:
        print(f"    → {removed}건 제외, {len(valid_items)}건 유효")
    else:
        print(f"    → 모두 유효 ({len(valid_items)}건)")

    data["news"] = valid_items
    return data


def call_claude(prompt, api_key):
    payload = json.dumps({
        "model": "claude-sonnet-5-5",
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())

    if "error" in result:
        raise RuntimeError(f"Claude API 오류: {result['error']}")

    for block in result.get("content", []):
        if block.get("type") == "text":
            return block["text"]

    raise RuntimeError(f"Claude 응답에 텍스트 없음: {json.dumps(result)[:300]}")


def create_cover_image(week, month, year):
    """전문적인 CSO 뉴스 커버 이미지 생성 (1920×900 PNG)."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 1920, 900

        # 그라데이션 배경 (진한 남색 → 네이비)
        pixels = []
        for y in range(H):
            t = y / H
            pixels.extend([int(13 + t * 5), int(22 + t * 18), int(60 + t * 28)] * W)
        img = Image.frombytes('RGB', (W, H), bytes(pixels))
        draw = ImageDraw.Draw(img)

        # 상단·하단 골드 라인
        draw.rectangle([(0, 0), (W, 7)], fill=(212, 175, 55))
        draw.rectangle([(0, H - 7), (W, H)], fill=(212, 175, 55))

        # 우측 장식용 원형 패턴
        for cx, cy, cr, col in [
            (1350, 160, 190, (18, 55, 120)),
            (1640, 290, 245, (14, 45, 105)),
            (1840, 95,  160, (22, 62, 130)),
            (1160, 460, 140, (16, 50, 115)),
            (1490, 560, 205, (20, 58, 125)),
            (1770, 660, 175, (12, 42, 100)),
            (1210, 730, 120, (24, 65, 135)),
            (1590, 810, 155, (17, 52, 118)),
        ]:
            draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr],
                         fill=col, outline=(60, 90, 155), width=2)

        # 세로 구분선
        draw.rectangle([(880, 60), (883, H - 60)], fill=(60, 90, 155))

        # 한글 폰트 탐색
        font_candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]

        def get_font(size):
            for fp in font_candidates:
                if os.path.exists(fp):
                    try:
                        return ImageFont.truetype(fp, size)
                    except Exception:
                        pass
            return ImageFont.load_default()

        # 좌측 메인 텍스트
        draw.text((80, 90),  "CSO",                              font=get_font(190), fill=(80, 165, 255))
        draw.text((80, 305), "주간 뉴스",                        font=get_font(105), fill=(255, 255, 255))
        draw.text((80, 450), f"W{week}  ·  {year}년 {month}월", font=get_font(55),  fill=(175, 200, 225))
        draw.text((80, 540), "의약품 판촉영업 CSO 전문 뉴스레터", font=get_font(38),  fill=(130, 160, 195))
        draw.text((80, 615), "ProMR | promr.co.kr",              font=get_font(34),  fill=(100, 140, 175))

        # 우측 카테고리 안내
        draw.text((930, 110), "이번 주 핵심 이슈",        font=get_font(52), fill=(180, 210, 235))
        draw.text((930, 205), "• CSO 규제·정책 변화",     font=get_font(43), fill=(150, 190, 218))
        draw.text((930, 270), "• 수수료·정산 구조",       font=get_font(43), fill=(150, 190, 218))
        draw.text((930, 335), "• 제네릭 약가 동향",       font=get_font(43), fill=(150, 190, 218))
        draw.text((930, 400), "• 제약영업 실무 인사이트", font=get_font(43), fill=(150, 190, 218))

        os.makedirs("covers", exist_ok=True)
        path = f"covers/W{week}.png"
        img.save(path, 'PNG', optimize=True)
        print(f"  ✅ 커버 이미지 생성: {path}")
        return path

    except ImportError:
        print("  ⚠️ Pillow 미설치 — 기본 커버 이미지 사용.")
        return None
    except Exception as e:
        print(f"  ⚠️ 커버 이미지 생성 실패 ({type(e).__name__}: {e})")
        return None


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY가 없습니다. GitHub Secret에 추가해주세요.")
        sys.exit(1)

    week_override = sys.argv[1] if len(sys.argv) > 1 else None
    year, week, month = get_week_info(week_override)
    output_file = f"cso_news_data_W{week}.json"

    if os.path.exists(output_file):
        print(f"  ℹ️  {output_file} 이미 존재합니다. 건너뜁니다.")
        sys.exit(0)

    today = datetime.date.today()
    print(f"📰 {year}년 {month}월 {week}주차 뉴스 수집 중... (기준일: {today}, 최근 30일 이내)")

    queries = [
        "CSO 제약 영업 규제",
        "CSO 수수료 위탁판매",
        "제약 CSO 신고제 정책",
        "제네릭 약가 제약 영업",
        "제약 영업대행 계약",
    ]

    all_items = []
    seen_titles = set()
    for query in queries:
        items = fetch_google_news_rss(query, max_items=15)
        for item in items:
            if item["title"] not in seen_titles:
                seen_titles.add(item["title"])
                all_items.append(item)

    print(f"  수집 완료: {len(all_items)}건")

    if not all_items:
        print("❌ 최근 30일 이내 뉴스를 수집하지 못했습니다.")
        sys.exit(1)

    print("  🤖 Claude AI 요약 및 인사이트 생성 중...")

    news_text = "\n".join([
        f"{i+1}. {item['title']}\n   URL: {item['url']}\n   출처: {item['source']} | {item['date']}\n   내용: {item['description'][:150]}"
        for i, item in enumerate(all_items[:40])
    ])

    prompt = f"""다음은 {year}년 {month}월 {week}주차({today} 기준) CSO(의약품 판촉영업 위탁, Contract Sales Organization) 관련 한국 뉴스 목록입니다.

{news_text}

[선별 규칙]
1. 반드시 pubDate 기준으로 가장 최신 기사 우선 선별하세요.
2. CSO·제약영업 종사자에게 실질적으로 중요한 뉴스만 선별하세요.
3. 중복 뉴스는 1건만 포함하세요.
4. 가능한 한 10건을 선별하되, 품질이 낮은 기사를 넣느니 적더라도 좋은 기사를 선택하세요.
5. date 필드는 반드시 pubDate를 YYYY.MM.DD 형식으로 변환하여 정확히 기입하세요.
6. URL은 목록에 있는 그대로 복사하세요 (변형 금지).

반드시 아래 JSON만 출력하세요 (설명·마크다운 없이):

{{
  "year": "{year}",
  "week": "{week}",
  "month": "{month}",
  "news": [
    {{
      "title": "뉴스 원본 제목",
      "url": "원문 URL (목록에 있는 그대로)",
      "date": "YYYY.MM.DD",
      "source": "언론사명",
      "summary": "2문장 이내. 핵심 사실만.",
      "insight": "1문장. ProMR(EDI 자동정산·CSO 신고제 대응·계약 5년 보관) 활용 팁 포함 가능."
    }}
  ]
}}

선별 기준: CSO 규제·제도변화 > 수수료·정산 > 제네릭 약가·품목 > 제약사 영업구조."""

    try:
        response = call_claude(prompt, api_key)
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        data = json.loads(response)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"❌ Claude API 오류 HTTP {e.code}: {body[:300]}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 파싱 오류: {e}")
        print(f"   Claude 응답 (처음 500자): {response[:500]}")
        sys.exit(1)

    # 품질 검증
    data = validate_and_clean_news(data, year, month)

    if not data.get("news"):
        print("❌ 품질 검증 후 유효한 뉴스가 없습니다.")
        sys.exit(1)

    # 커버 이미지 생성 (커밋 전에 생성해야 GitHub raw URL이 유효)
    cover_path = create_cover_image(week, month, year)
    if cover_path:
        data["cover_image_url"] = f"https://raw.githubusercontent.com/tntbrain1/NEWS/main/{cover_path}"
        data["cover_local_path"] = cover_path
    else:
        data["cover_image_url"] = "https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=1920&h=900&fit=crop&q=90"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    count = len(data.get("news", []))
    print(f"  ✅ {output_file} 생성 완료 ({count}건)")


if __name__ == "__main__":
    main()
