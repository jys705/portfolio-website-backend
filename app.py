from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
import time
import re  # 정규식 모듈 추가

app = Flask(__name__)
CORS(app)

# OpenAI API KEY
OPENAI_API_KEY = ""
ASSISTANT_ID = ""

# 메타데이터 태그 제거 함수
def clean_assistant_response(text):
    # 【숫자:숫자†source】 형식의 메타데이터 제거
    cleaned_text = re.sub(r'【\d+:\d+†source】', '', text)
    # 다른 형식의 메타데이터도 제거 가능
    return cleaned_text

@app.route('/sendMessage', methods=['POST'])
def send_message():
    try:
        # JSON 방식으로 받기
        user_message = request.json.get('message')
        thread_id = request.json.get('thread_id')
        print(f"클라이언트가 보낸 메시지: {user_message}")
        print(f"스레드 ID: {thread_id}")

        # 1. 스레드가 없는 경우 새로운 스레드 생성
        if not thread_id:
            thread_response = requests.post(
                "https://api.openai.com/v1/threads",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                    "OpenAI-Beta": "assistants=v2"
                },
                json={}
            )
            thread_data = thread_response.json()
            print(f"스레드 생성 응답: {thread_data}")
            
            if "error" in thread_data:
                return jsonify({
                    "error": f"스레드 생성 오류: {thread_data['error']['message']}"
                }), 500
                
            thread_id = thread_data.get("id")
            if not thread_id:
                return jsonify({
                    "error": "스레드 ID를 찾을 수 없습니다."
                }), 500
                
            print(f"새 스레드 생성: {thread_id}")

        # 2. 스레드에 메시지 추가
        message_response = requests.post(
            f"https://api.openai.com/v1/threads/{thread_id}/messages",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "assistants=v2"
            },
            json={
                "role": "user",
                "content": user_message
            }
        )
        message_data = message_response.json()
        print(f"메시지 추가 응답: {message_data}")
        
        if "error" in message_data:
            return jsonify({
                "error": f"메시지 추가 오류: {message_data['error']['message']}"
            }), 500
        
        # 3. 어시스턴트 실행
        run_response = requests.post(
            f"https://api.openai.com/v1/threads/{thread_id}/runs",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "assistants=v2"
            },
            json={
                "assistant_id": ASSISTANT_ID
            }
        )
        run_data = run_response.json()
        print(f"실행 응답: {run_data}")
        
        if "error" in run_data:
            return jsonify({
                "error": f"실행 오류: {run_data['error']['message']}"
            }), 500
            
        run_id = run_data.get("id")
        if not run_id:
            return jsonify({
                "error": "실행 ID를 찾을 수 없습니다."
            }), 500
        
        # 4. 실행 완료 대기
        max_attempts = 30  # 최대 30초 대기
        attempts = 0
        status = ""
        
        while attempts < max_attempts:
            run_status_response = requests.get(
                f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "assistants=v2"
                }
            )
            run_status_data = run_status_response.json()
            print(f"상태 확인 응답: {run_status_data}")
            
            if "error" in run_status_data:
                return jsonify({
                    "error": f"상태 확인 오류: {run_status_data['error']['message']}"
                }), 500
                
            status = run_status_data.get("status", "")
            print(f"현재 상태: {status}")
            
            if status in ["completed", "failed", "cancelled", "expired"]:
                break
            
            time.sleep(1)
            attempts += 1
        
        # 5. 어시스턴트의 응답 가져오기
        if status == "completed":
            messages_response = requests.get(
                f"https://api.openai.com/v1/threads/{thread_id}/messages",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "assistants=v2"
                }
            )
            messages_data = messages_response.json()
            print(f"메시지 응답: {messages_data}")
            
            if "error" in messages_data:
                return jsonify({
                    "error": f"메시지 가져오기 오류: {messages_data['error']['message']}"
                }), 500
            
            # 가장 최근 어시스턴트 메시지 찾기
            assistant_message = None
            for message in messages_data.get("data", []):
                if message.get("role") == "assistant":
                    assistant_message = message
                    break
            
            if assistant_message:
                content_list = assistant_message.get("content", [])
                if content_list and len(content_list) > 0:
                    text_content = content_list[0].get("text", {})
                    assistant_content = text_content.get("value", "응답 내용을 찾을 수 없습니다.")
                    
                    # 메타데이터 태그 제거
                    cleaned_content = clean_assistant_response(assistant_content)
                    
                    return jsonify({
                        "response": cleaned_content,
                        "thread_id": thread_id
                    })
        
        if status == "failed":
            return jsonify({
                "error": "어시스턴트 실행이 실패했습니다.",
                "thread_id": thread_id
            }), 500
        elif status == "expired":
            return jsonify({
                "error": "어시스턴트 실행 시간이 만료되었습니다.",
                "thread_id": thread_id
            }), 500
        else:
            return jsonify({
                "error": f"응답을 받지 못했습니다. 상태: {status}",
                "thread_id": thread_id
            }), 500
    
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        return jsonify({
            "error": f"서버 오류: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)


