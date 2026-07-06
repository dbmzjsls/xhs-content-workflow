from app.services import content_rules


def test_revised_draft_enforces_xhs_brand_and_tags():
    brief = content_rules.normalize_brief({
        "topic": "睡前20分钟改作文",
        "audience": "雅思考生",
        "product_function": "Writing Checker",
        "pain_point": "改了5遍还是不知道卡在哪",
        "style_preference": "备忘录聊天框风",
    })
    route = content_rules.route_style(brief)
    plan = content_rules.build_narrative_plan(brief, route)
    draft = content_rules.generate_mock_draft(brief, plan)
    revised = content_rules.revise_draft(
        draft,
        content_rules.xhs_quality_check(draft),
        content_rules.humanize_check(draft),
    )
    report = content_rules.xhs_quality_check(revised)

    assert "Cathoven猫多芬雅思" in revised["body"]
    assert revised["body"].count("Cathoven猫多芬雅思") == 1
    assert "#猫多芬雅思" in revised["tags"]
    assert "#cathovenielts" in revised["tags"]
    assert 20 <= len(revised["body"]) <= 400
    assert report["passed"]


def test_humanize_check_catches_formal_and_hard_sell_words():
    report = content_rules.humanize_check({
        "title": "雅思作文神器",
        "body": "首先，这个绝绝子神器强烈推荐给大家。",
        "tags": [],
    })

    assert not report["passed"]
    assert any("书面词" in issue for issue in report["issues"])
    assert any("硬广" in issue for issue in report["issues"])


def test_quality_check_requires_first_brand_mention_to_be_full_name():
    report = content_rules.xhs_quality_check({
        "title": "睡前改作文",
        "body": (
            "晚上书桌前，我先试了 Cathoven。后来才知道 "
            "Cathoven猫多芬雅思 可以把问题拆开看。"
        ),
        "tags": ["#猫多芬雅思", "#cathovenielts"],
    })

    assert not report["passed"]
    assert any("首次产品名" in issue for issue in report["issues"])


def test_revision_keeps_required_brand_when_body_is_too_long():
    draft = {
        "title": "睡前20分钟改作文",
        "body": "晚上书桌前，我又开始改作文。" + "这段一直不知道问题在哪里，" * 60,
        "tags": ["#雅思写作"],
        "first_comment": "先改一段。",
    }
    revised = content_rules.revise_draft(
        draft,
        content_rules.xhs_quality_check(draft),
        content_rules.humanize_check(draft),
    )
    report = content_rules.xhs_quality_check(revised)

    assert len(revised["body"]) <= 400
    assert revised["body"].count("Cathoven猫多芬雅思") == 1
    assert report["passed"]
