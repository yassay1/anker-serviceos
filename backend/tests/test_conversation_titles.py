from serviceos_api.application.conversation_titles import conversation_title


def test_title_extracts_first_question_without_another_model_call():
    assert conversation_title('您好，我的充电宝充电时断断续续，该怎么排查？') == '充电宝充电时断断续续'
    assert conversation_title('Anker 737 无法开机') == 'Anker 737 无法开机'


def test_title_is_bounded_and_omits_contacts_and_links():
    assert conversation_title('你好') == '售后咨询'
    assert conversation_title('') == '新会话'
    title = conversation_title('我的设备无法开机，电话13800138000，联系a@example.com https://example.com/private')
    assert len(title) <= 24
    assert all(value not in title for value in ['13800138000', '@', 'https://'])
