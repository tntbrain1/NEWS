#!/usr/bin/env python3
"""
CSO 위클리 매거진 → Wix Blog 자동 발행 스크립트
사용: python3 publish_wix_blog.py <JSON_FILE> <API_KEY> <SITE_ID>
"""
import sys
import json
import urllib.request
import urllib.error
import uuid

def nid():
    return str(uuid.uuid4()).replace("-", "")[:8]

def text_node(text, bold=False, link_url=None):
    decorations = []
    if bold:
        decorations.append({"type": "BOLD"})
    if link_url:
        decorations.append({"type": "LINK", "linkData": {"link": {"url": link_url, "target": "_BLANK"}}})
    return {
        "type": "TEXT",
        "id": nid(),
        "nodes": [],
        "textData": {"text": text, "decorations": decorations}
    }

def paragraph(*text_nodes):
    return {"type": "PARAGRAPH", "id": nid(), "nodes": list(text_nodes), "paragraphData": {}}

def heading(text, level=2):
    return {
        "type": "HEADING",
        "id": nid(),
        "nodes": [text_node(text)],
        "headingData": {"level": level, "indentation": 0}
    }

def divider():
    return {"type": "DIVIDER", "id": nid(), "nodes": [], "dividerData": {"lineStyle": "SINGLE", "width": "LARGE", "alignment": "CENTER"}}

def build_rich_content(data):
    nodes = []
    year = data.get("year", "")
    week = data.get("week", "")
    month = data.get("month", "")

    # 소개 섹션
    nodes.append(paragraph(
        text_node(f"📰 {year}년 {month}월 {week}주차 CSO 업계 핵심 뉴스 {len(data['news'])}건을 선별했습니다.", bold=True)
    ))
    nodes.append(paragraph(
        text_node("CSO·제약영업 종사자를 위한 주간 뉴스 큐레이션입니다. 각 뉴스의 실무 인사이트를 함께 확인하세요.")
    ))
    nodes.append(divider())

    # 각 뉴스 아이템
    for i, item in enumerate(data['news'], 1):
        nodes.append(heading(f"{i}. {item['title']}", level=3))
        nodes.append(paragraph(
            text_node("출처: ", bold=True),
            text_node(f"{item['source']} | {item['date']}")
        ))
        nodes.append(paragraph(text_node(item['summary'])))
        if item.get('insight'):
            nodes.append(paragraph(
                text_node("💡 CSO 실무 인사이트: ", bold=True),
                text_node(item['insight'])
            ))
        nodes.append(paragraph(
            text_node("📎 원문 보기", link_url=item['url'])
        ))
        nodes.append(divider())

    # ProMR CTA
    nodes.append(heading("ProMR — CSO·CMR 전용 제약영업 SaaS 플랫폼", level=3))
    nodes.append(paragraph(
        text_node("EDI 자동정산 · CSO 신고제 완벽 대응 · 계약·지출 5년 보관 · 특허 등록")
    ))
    nodes.append(paragraph(
        text_node("🚀 ProMR 무료로 시작하기", link_url="https://promr.co.kr")
    ))

    return {"nodes": nodes}


def get_categories(api_key, site_id):
    req = urllib.request.Request(
        "https://www.wixapis.com/blog/v3/categories?paging.limit=50",
        headers={"Authorization": api_key, "wix-site-id": site_id}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read())
    categories = d.get("categories", [])
    # 업계뉴스 카테고리 찾기
    for cat in categories:
        label = cat.get("label", "")
        if "업계" in label or "뉴스" in label or "news" in label.lower() or "industry" in label.lower():
            return cat.get("id")
    # 못 찾으면 첫 번째 카테고리 반환
    if categories:
        print(f"  ℹ️  '업계뉴스' 카테고리 없음. 첫 번째 카테고리 사용: {categories[0].get('label')}")
        return categories[0].get("id")
    return None


def create_draft(api_key, site_id, title, rich_content, category_id, cover_image_url=None):
    draft = {
        "title": title,
        "richContent": rich_content,
    }
    if category_id:
        draft["categoryIds"] = [category_id]
    if cover_image_url:
        draft["media"] = {"wixMedia": {"image": {"imageInfo": {"url": cover_image_url}}}}

    body = json.dumps({"draft": draft}).encode("utf-8")
    req = urllib.request.Request(
        "https://www.wixapis.com/blog/v3/posts/drafts",
        data=body,
        method="POST",
        headers={
            "Authorization": api_key,
            "wix-site-id": site_id,
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def publish_draft(api_key, site_id, draft_id):
    req = urllib.request.Request(
        f"https://www.wixapis.com/blog/v3/posts/drafts/{draft_id}/publish",
        data=b"{}",
        method="POST",
        headers={
            "Authorization": api_key,
            "wix-site-id": site_id,
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    if len(sys.argv) < 4:
        print("사용법: python3 publish_wix_blog.py <JSON_FILE> <API_KEY> <SITE_ID>")
        sys.exit(1)

    json_file = sys.argv[1]
    api_key = sys.argv[2]
    site_id = sys.argv[3]

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    year = data.get("year", "")
    week = data.get("week", "")
    month = data.get("month", "")
    title = f"CSO 위클리 매거진 | {year}년 {month}월 {week}주차"

    print(f"📝 블로그 발행 시작: {title}")
    print(f"   뉴스 항목: {len(data.get('news', []))}건")

    # 1. 카테고리 조회
    print("  1. 카테고리 조회 중...")
    try:
        category_id = get_categories(api_key, site_id)
        print(f"     카테고리 ID: {category_id}")
    except Exception as e:
        print(f"     ⚠️  카테고리 조회 실패 (계속 진행): {e}")
        category_id = None

    # 2. Rich Content 생성
    print("  2. 본문 구성 중...")
    rich_content = build_rich_content(data)

    # 3. 드래프트 생성
    print("  3. 드래프트 생성 중...")
    try:
        draft_resp = create_draft(api_key, site_id, title, rich_content, category_id)
        draft_id = draft_resp.get("draft", {}).get("id")
        if not draft_id:
            print(f"  ❌ 드래프트 생성 실패: {json.dumps(draft_resp, ensure_ascii=False)[:200]}")
            sys.exit(1)
        print(f"     드래프트 ID: {draft_id}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ❌ 드래프트 생성 실패 HTTP {e.code}: {body[:300]}")
        sys.exit(1)

    # 4. 발행
    print("  4. 발행 중...")
    try:
        pub_resp = publish_draft(api_key, site_id, draft_id)
        post_id = pub_resp.get("post", {}).get("id", "")
        slug = pub_resp.get("post", {}).get("slug", "")
        print(f"  ✅ 블로그 발행 완료!")
        print(f"     포스트 ID: {post_id}")
        print(f"     URL: https://www.promr.blog/resources/{slug}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ❌ 발행 실패 HTTP {e.code}: {body[:300]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
