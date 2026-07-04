import streamlit as st
import pandas as pd
from database import get_connection
import uuid
import datetime

st.set_page_config(page_title="Hệ Thống Quản Lý Văn Bản", page_icon="📄", layout="wide")

st.markdown("""
<style>
    .stMetric {
        background-color: #1E293B;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        transition: transform 0.3s ease;
    }
    .stMetric:hover { transform: translateY(-5px); border-color: rgba(255, 255, 255, 0.3); }
    h1 {
        background: -webkit-linear-gradient(45deg, #3b82f6, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

st.title("Hệ Thống Quản Lý Văn Bản Điều Hành")

def match_documents():
    conn = get_connection()
    try:
        incoming_docs = conn.execute("SELECT * FROM documents WHERE type = 'INCOMING'").fetchall()
        outgoing_docs = conn.execute("SELECT * FROM documents WHERE type = 'OUTGOING'").fetchall()
        
        updated_count = 0
        for incoming in incoming_docs:
            current_status = "Đang nhận việc"
            matched_out_id = None
            
            # Match
            matched_out = next((out for out in outgoing_docs if incoming['document_no'] in (out['summary'] or '') or (out['content'] and incoming['document_no'] in out['content'])), None)
            
            if matched_out:
                current_status = "Có văn bản đi"
                matched_out_id = matched_out['id']
            else:
                is_overdue = incoming['deadline'] and datetime.datetime.now() > datetime.datetime.fromisoformat(incoming['deadline'])
                tasks = conn.execute("SELECT * FROM tasks WHERE document_id = ?", (incoming['id'],)).fetchall()
                has_pending = any(t['status'] != 'Hoàn thành' for t in tasks)
                
                if is_overdue or (not has_pending and len(tasks) > 0):
                    current_status = "Chưa có văn bản trả lời"
                else:
                    current_status = "Đang nhận việc"
            
            relation = conn.execute("SELECT id FROM document_relations WHERE incoming_id = ?", (incoming['id'],)).fetchone()
            if not relation:
                conn.execute("INSERT INTO document_relations (id, incoming_id, outgoing_id, match_status) VALUES (?, ?, ?, ?)",
                             (str(uuid.uuid4()), incoming['id'], matched_out_id, current_status))
            else:
                conn.execute("UPDATE document_relations SET outgoing_id = ?, match_status = ? WHERE id = ?",
                             (matched_out_id, current_status, relation['id']))
            updated_count += 1
            
        conn.commit()
        return updated_count
    finally:
        conn.close()

def generate_mock_data():
    conn = get_connection()
    try:
        # Clear old data
        conn.execute("DELETE FROM document_relations")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM documents")
        
        # Insert Incoming
        conn.execute("INSERT INTO documents (id, type, document_no, summary, deadline) VALUES ('in1', 'INCOMING', '123/UBND', 'V/v báo cáo tiến độ dự án', '2027-12-31 23:59:59')")
        conn.execute("INSERT INTO documents (id, type, document_no, summary, deadline) VALUES ('in2', 'INCOMING', '456/STT', 'Yêu cầu phúc đáp công văn', '2022-01-01 23:59:59')")
        conn.execute("INSERT INTO documents (id, type, document_no, summary, deadline) VALUES ('in3', 'INCOMING', '789/VP', 'Xin ý kiến chỉ đạo của Giám đốc', '2027-12-31 23:59:59')")
        
        # Insert Outgoing
        conn.execute("INSERT INTO documents (id, type, document_no, summary) VALUES ('out1', 'OUTGOING', '102/UBND-TL', 'Trả lời công văn 789/VP')")
        
        # Insert Tasks
        conn.execute("INSERT INTO tasks (id, document_id, assignee, status) VALUES ('t1', 'in1', 'Nguyễn Văn A', 'Đang xử lý')")
        conn.execute("INSERT INTO tasks (id, document_id, assignee, status) VALUES ('t2', 'in3', 'Trần Thị B', 'Hoàn thành')")
        
        conn.commit()
    finally:
        conn.close()

col_btn1, col_btn2 = st.columns([1, 1])

with col_btn1:
    if st.button("🔄 Đồng bộ & Đối chiếu Dữ liệu", type="primary", use_container_width=True):
        with st.spinner("Đang chạy đối chiếu tự động..."):
            updated = match_documents()
            st.success(f"Đã đối chiếu thành công {updated} văn bản đến!")

with col_btn2:
    if st.button("📥 Nạp dữ liệu Test mẫu", use_container_width=True):
        with st.spinner("Đang nạp dữ liệu..."):
            generate_mock_data()
            match_documents()
            st.success("Đã nạp dữ liệu mẫu thành công! Vui lòng làm mới lại trang.")

st.markdown("---")

conn = get_connection()
relations = conn.execute('''
    SELECT 
        r.match_status,
        i.document_no as inc_doc,
        i.summary as inc_summary,
        o.document_no as out_doc,
        i.id as inc_id
    FROM document_relations r
    JOIN documents i ON r.incoming_id = i.id
    LEFT JOIN documents o ON r.outgoing_id = o.id
''').fetchall()

if len(relations) == 0:
    st.info("Cơ sở dữ liệu đang trống. Dưới đây là dữ liệu mẫu để hiển thị giao diện.")
    stats = {"Đang nhận việc": 12, "Chưa có văn bản trả lời": 3, "Có văn bản đi": 25}
    data = [
        {"Văn bản đến": "123/UBND", "Trích yếu": "V/v báo cáo quý 1", "Trạng thái": "Đang nhận việc", "Người xử lý": "Nguyễn Văn A", "VB Đi": "-"},
        {"Văn bản đến": "456/STT", "Trích yếu": "Yêu cầu phúc đáp", "Trạng thái": "Chưa có văn bản trả lời", "Người xử lý": "Chưa phân công", "VB Đi": "-"},
        {"Văn bản đến": "789/VP", "Trích yếu": "Xin ý kiến chỉ đạo", "Trạng thái": "Có văn bản đi", "Người xử lý": "Trần Thị B", "VB Đi": "102/UBND-TL"},
    ]
else:
    stats = {"Đang nhận việc": 0, "Chưa có văn bản trả lời": 0, "Có văn bản đi": 0}
    data = []
    for rel in relations:
        stats[rel['match_status']] = stats.get(rel['match_status'], 0) + 1
        
        tasks = conn.execute("SELECT assignee FROM tasks WHERE document_id = ?", (rel['inc_id'],)).fetchall()
        assignees = ", ".join([t['assignee'] for t in tasks if t['assignee']]) if tasks else "Chưa phân công"
        
        data.append({
            "Văn bản đến": rel['inc_doc'],
            "Trích yếu": rel['inc_summary'],
            "Trạng thái": rel['match_status'],
            "Người xử lý": assignees,
            "VB Đi": rel['out_doc'] if rel['out_doc'] else "-"
        })
conn.close()

col1, col2, col3 = st.columns(3)
col1.metric("Đang nhận việc", stats.get("Đang nhận việc", 0))
col2.metric("Chưa có VB trả lời", stats.get("Chưa có văn bản trả lời", 0))
col3.metric("Có văn bản đi", stats.get("Có văn bản đi", 0))

st.markdown("### Danh sách văn bản đối chiếu")
df = pd.DataFrame(data)

def color_status(val):
    if val == 'Đang nhận việc': return 'color: #fde047; font-weight: bold;'
    elif val == 'Chưa có văn bản trả lời': return 'color: #fca5a5; font-weight: bold;'
    elif val == 'Có văn bản đi': return 'color: #6ee7b7; font-weight: bold;'
    return ''
    
if not df.empty:
    st.dataframe(df.style.map(color_status, subset=['Trạng thái']), use_container_width=True, hide_index=True)
