import sqlite3
import pandas as pd
from github import Github
from github.GithubException import UnknownObjectException
import os
import sys

# ==========================================
# 🛠️ CẤU HÌNH GITHUB
# ==========================================
# Thay thế chuỗi bên dưới bằng Personal Access Token của bạn
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "YOUR_GITHUB_TOKEN_HERE")
# Thay thế bằng tên kho lưu trữ GitHub của bạn (ví dụ: leanhduchwru-ux/quan-ly-van-ban)
REPO_NAME = "leanhduchwru-ux/quan-ly-van-ban" 

def get_connection():
    conn = sqlite3.connect('local_db.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn

def setup_labels(repo):
    print("--- 🏷️ Khởi tạo bộ Nhãn (Labels) chuẩn ---")
    required_labels = [
        {"name": "Status: Pending", "color": "eab308", "description": "Văn bản đang chờ xử lý"},
        {"name": "Priority: High", "color": "ef4444", "description": "Xử lý khẩn cấp"},
        {"name": "Type: Incoming", "color": "3b82f6", "description": "Văn bản đến"}
    ]
    
    for lbl in required_labels:
        try:
            repo.get_label(lbl["name"])
            print(f"✅ Nhãn '{lbl['name']}' đã tồn tại.")
        except UnknownObjectException:
            repo.create_label(name=lbl["name"], color=lbl["color"], description=lbl["description"])
            print(f"✨ Đã tạo nhãn mới: '{lbl['name']}'")

def sync_to_github():
    print("🚀 Bắt đầu tiến trình đồng bộ Tồn đọng lên GitHub Issues...\n")
    
    if GITHUB_TOKEN == "YOUR_GITHUB_TOKEN_HERE":
        print("❌ LỖI NGHIÊM TRỌNG: Bạn chưa cấu hình GITHUB_TOKEN!")
        print("💡 Hướng dẫn: Mở file github_sync.py và dán mã token của bạn vào dòng 10.")
        sys.exit(1)

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
    except Exception as e:
        print(f"❌ Lỗi kết nối GitHub (Sai Token hoặc Tên Repo): {e}")
        sys.exit(1)
        
    setup_labels(repo)
    
    print("\n--- 📥 Đọc dữ liệu Tồn đọng từ Cơ sở dữ liệu ---")
    conn = get_connection()
    try:
        # Lấy danh sách các văn bản "Chưa có văn bản trả lời"
        unanswered_docs = conn.execute('''
            SELECT 
                i.content as system_name,
                i.document_no,
                i.summary,
                i.issued_date,
                t.assignee
            FROM document_relations r
            JOIN documents i ON r.incoming_id = i.id
            JOIN tasks t ON r.incoming_id = t.document_id
            WHERE r.match_status LIKE '%Chưa có%'
        ''').fetchall()
        
        if not unanswered_docs:
            print("🎉 Tuyệt vời! Không có văn bản nào tồn đọng. Không cần đồng bộ.")
            return

        print(f"🔍 Phát hiện {len(unanswered_docs)} văn bản tồn đọng. Đang đối chiếu với GitHub...")
        
        # Lấy danh sách Issues hiện tại để tránh tạo trùng
        open_issues = repo.get_issues(state='open')
        existing_issue_titles = [issue.title for issue in open_issues]
        
        created_count = 0
        for doc in unanswered_docs:
            doc_no = doc['document_no'] if doc['document_no'] else "Không số"
            summary = doc['summary'] if doc['summary'] else "Không có trích yếu"
            assignee = doc['assignee'] if doc['assignee'] else "Chưa rõ"
            sys_name = doc['system_name']
            
            # Tiêu đề Issue ngắn gọn để hiển thị trên bảng Kanban
            issue_title = f"[{sys_name}] {doc_no}"
            if summary and summary != "Không có trích yếu":
                issue_title += f" - {summary[:60]}..."
            
            # Tránh trùng lặp (Kiểm tra Ký hiệu)
            is_duplicate = any(doc_no in title for title in existing_issue_titles if doc_no != "Không số")
            
            if is_duplicate:
                print(f"⏩ Bỏ qua (Đã có trên Kanban): {doc_no}")
                continue
                
            # Tạo nội dung mô tả chi tiết của Issue
            issue_body = f"""### 📄 Chi tiết Khối lượng công việc (Tồn đọng)

**Căn cứ pháp lý / Nguồn:** `{sys_name}`
**Số / Ký hiệu:** `{doc_no}`
**Ngày tiếp nhận:** {doc['issued_date']}

🎯 **Trách nhiệm giải quyết:** 
### **{assignee}**

---
**Trích yếu nội dung chỉ đạo:**
> {summary}

---
*Văn bản này đang quá hạn hoặc chưa có công văn trả lời. Đề nghị chuyên viên khẩn trương xử lý và chuyển trạng thái trên bảng Kanban.*
"""
            print(f"⏳ Đang tạo thẻ Kanban cho: {doc_no}...")
            issue = repo.create_issue(
                title=issue_title,
                body=issue_body,
                labels=["Status: Pending", "Priority: High", "Type: Incoming"]
            )
            print(f"✅ Thành công! Issue #{issue.number} (Giao cho: {assignee})")
            created_count += 1
            
        print(f"\n🏁 Đồng bộ hoàn tất! Đã khởi tạo {created_count} thẻ Kanban mới.")
            
    finally:
        conn.close()

if __name__ == "__main__":
    sync_to_github()
