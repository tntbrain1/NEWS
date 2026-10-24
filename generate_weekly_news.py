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
import re
import xml.etree.ElementTree as ET


def get_week_info(week_override=None):
    today = datetime.date.today()
    year, week, _ = today.isocalendar()
    month = today.month
    if week_override:
        week = int(week_override)
    return str(year), str(week), str(month)


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
            if title and link:
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


def call_claude(prompt, api_key):
    payload = json.dumps({
        "model": "claude-sonnet-5-5",
        "max_tokens": 4096,
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

    print(f"📰 {year}년 {month}월 {week}주차 뉴스 수집 중...")

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
        print("❌ 뉴스를 수집하지 못했습니다.")
        sys.exit(1)

    print("  🤖 Claude AI 요약 및 인사이트 생성 중...")

    news_text = "\n".join([
        f"{i+1}. {item['title']}\n   URL: {item['url']}\n   날짜: {item['date']}\n   출처: {item['source']}\n   내용: {item['description']}"
        for i, item in enumerate(all_items[:60])
    ])

    prompt = f"""다음은 이번 주 CSO(의약품 판촉영업 위탁, Contract Sales Organization) 관련 한국 뉴스 목록입니다.

{news_text}

위에서 CSO·제약영업 종사자에게 중요한 뉴스 10~15건을 선별하고, 반드시 아래 JSON만 출력하세요 (설명·마크다운 없이):

{{
  "year": "{year}",
  "week": "{week}",
  "month": "{month}",
  "news": [
    {{
      "title": "뉴스 원본 제목",
      "url": "원문 URL (목록에 있는 그대로)",
      "date": "YYYY.MM.DD 형식",
      "source": "언론사명",
      "summary": "3~4문장. 핵심 사실과 CSO 업계 영향 위주로.",
      "insight": "CSO 실무자가 지금 취해야 할 행동. ProMR(EDI 자동정산·CSO 신고제 대응·계약 5년 보관) 활용 팁 포함 가능."
    }}
  ]
}}

선별 기준: CSO 규제·제도변화 > 수수료·정산 > 제네릭 약가·품목 > 제약사 영업구조. 중복 유사 뉴스는 1건만."""

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
        sys.exit(1)

    data["cover_image_url"] = "https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=1920&h=900&fit=crop&q=90"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {output_file} 생성 완료 ({len(data.get('news', []))}건)")


if __name__ == "__main__":
    main()
