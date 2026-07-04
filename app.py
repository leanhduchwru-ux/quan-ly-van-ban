import streamlit as st
import pandas as pd
from database import get_connection
import uuid
import datetime
import io
import re

st.set_page_config(page_title="Hệ Thống Quản Lý Văn Bản", page_icon="📄", layout="wide")

st.markdown("""
<style>
    h1 {
        background: -webkit-linear-gradient(45deg, #3b82f6, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

st.title("Hệ Thống Quản Lý Văn Bản Điều Hành")

st.markdown("### 📥 Nạp dữ liệu từ File Excel")
st.markdown("Vui lòng tải lên file danh sách xuất ra từ hệ thống. File cần có các cột chứa chữ **'Ký hiệu'** và **'Trích yếu'**.")

def process_uploaded_file(file, doc_type, system_name):
    if file is not None:
        try:
            df = pd.read_excel(file, header=None)
            conn = get_connection()
            count = 0
            raw_count = 0
            
            # Xóa dữ liệu cũ của riêng Hệ thống này (VOFFICE hoặc HPNET) để tránh trùng lặp
            conn.execute("DELETE FROM documents WHERE type = ? AND content = ?", (doc_type, system_name))
            
            # Lấy danh sách văn bản đã có để tránh trùng lặp
            existing_docs = set()
            for r in conn.execute("SELECT document_no, summary FROM documents WHERE type = ?", (doc_type,)).fetchall():
                key = f"{str(r['document_no']).strip().lower()}_{str(r['summary']).strip().lower()}"
                existing_docs.add(key)
            
            doc_col = -1
            summary_col = -1
            assignee_col = -1
            date_col = -1
            agency_col = -1
            
            for index, row in df.iterrows():
                # Bươc 1: Dò tìm dòng chứa Tiêu đề cột
                if doc_col == -1 or summary_col == -1:
                    for i, val in enumerate(row):
                        if pd.notna(val):
                            val_str = str(val).lower()
                            if 'ký hiệu' in val_str or 's.k.h' in val_str:
                                doc_col = i
                            if 'trích yếu' in val_str:
                                summary_col = i
                            if 'xử lý' in val_str or 'người nhận' in val_str or 'chuyển' in val_str:
                                assignee_col = i
                            if 'ngày ban hành' in val_str or 'ngày nhận' in val_str or 'ngày văn bản' in val_str or 'ngày' in val_str.split():
                                date_col = i
                            if 'nơi ban hành' in val_str or 'nơi lưu trữ' in val_str or 'nơi nhận' in val_str or 'cơ quan' in val_str:
                                agency_col = i
                    continue
                
                # Bước 2: Đọc dữ liệu từ các dòng bên dưới
                if doc_col != -1 and summary_col != -1:
                    doc_number = str(row[doc_col]).strip() if pd.notna(row[doc_col]) else ""
                    summary = str(row[summary_col]).strip() if pd.notna(row[summary_col]) else ""
                    
                    doc_date = ""
                    if date_col != -1 and pd.notna(row[date_col]):
                        val = row[date_col]
                        if isinstance(val, datetime.datetime):
                            doc_date = val.strftime("%d/%m/%Y")
                        else:
                            doc_date = str(val).strip()
                            doc_date = doc_date.replace("00:00:00", "").strip()
                            
                    agency = str(row[agency_col]).strip() if agency_col != -1 and pd.notna(row[agency_col]) else ""
                    
                    if doc_number and doc_number.lower() not in ['nan', 'none', '']:
                        raw_count += 1
                        key_to_check = f"{doc_number.strip().lower()}_{summary.strip().lower()}"
                        if key_to_check not in existing_docs:
                            doc_id = str(uuid.uuid4())
                            conn.execute("INSERT INTO documents (id, type, document_no, issued_date, system_source, summary, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                         (doc_id, doc_type, doc_number, doc_date, agency, summary, system_name))
                            
                            if assignee_col != -1 and pd.notna(row[assignee_col]):
                                val = str(row[assignee_col]).strip()
                                parts = [p.strip() for p in re.split(r'[,\n;]', val) if p.strip()]
                                assignee = ""
                                
                                tm_index = -1
                                for i, p in enumerate(parts):
                                    if 'Trương Mạnh Tiến' in p:
                                        tm_index = i
                                        break
                                
                                if tm_index != -1 and tm_index < len(parts) - 1:
                                    assignee = parts[tm_index + 1]
                                elif tm_index == -1 and parts:
                                    filtered = [p for p in parts if p.lower() not in ['lưu', 'lưu trữ', 'văn thư', 'vt']]
                                    assignee = filtered[0] if filtered else parts[0]
                                else:
                                    assignee = "Trương Mạnh Tiến"
                                
                                assignee = re.sub(r'\(.*?\)', '', assignee).strip()
                                
                                conn.execute("INSERT INTO tasks (id, document_id, assignee, status) VALUES (?, ?, ?, ?)",
                                             (str(uuid.uuid4()), doc_id, assignee, 'Đang xử lý'))
                            
                            existing_docs.add(key_to_check)
                            count += 1
            
            if doc_col == -1 or summary_col == -1:
                st.error("File không đúng định dạng cấu trúc, vui lòng kiểm tra lại cột Ký hiệu hoặc Trích yếu")
                conn.close()
                return 0, 0
            
            conn.execute("INSERT OR REPLACE INTO app_stats (key, value) VALUES (?, ?)", 
                         (f"raw_count_{doc_type}_{system_name}", raw_count))

            conn.commit()
            conn.close()
            return count, raw_count
        except Exception as e:
            st.error(f"Lỗi đọc file: {e}")
            return 0, 0
    return 0, 0

col_up1, col_up2 = st.columns(2)

with col_up1:
    st.info("📥 VĂN BẢN ĐẾN")
    file_in_voffice = st.file_uploader("Kéo thả file Văn bản đến - VOFFICE", type=["xlsx", "xls"], key="in_voffice")
    if file_in_voffice:
        with st.spinner("Đang xử lý VOFFICE..."):
            c, raw = process_uploaded_file(file_in_voffice, 'INCOMING', 'VOFFICE')
            st.success(f"Đã nạp {c} văn bản đến VOFFICE (từ tổng số {raw} dòng trong file)!")
            
    file_in_hpnet = st.file_uploader("Kéo thả file Văn bản đến - HPNET", type=["xlsx", "xls"], key="in_hpnet")
    if file_in_hpnet:
        with st.spinner("Đang xử lý HPNET..."):
            c, raw = process_uploaded_file(file_in_hpnet, 'INCOMING', 'HPNET')
            st.success(f"Đã nạp {c} văn bản đến HPNET (từ tổng số {raw} dòng trong file)!")

with col_up2:
    st.info("📤 VĂN BẢN ĐI")
    file_out_voffice = st.file_uploader("Kéo thả file Văn bản đi - VOFFICE", type=["xlsx", "xls"], key="out_voffice")
    if file_out_voffice:
        with st.spinner("Đang xử lý VOFFICE..."):
            c, raw = process_uploaded_file(file_out_voffice, 'OUTGOING', 'VOFFICE')
            st.success(f"Đã nạp {c} văn bản đi VOFFICE (từ tổng số {raw} dòng trong file)!")
            
    file_out_hpnet = st.file_uploader("Kéo thả file Văn bản đi - HPNET", type=["xlsx", "xls"], key="out_hpnet")
    if file_out_hpnet:
        with st.spinner("Đang xử lý HPNET..."):
            c, raw = process_uploaded_file(file_out_hpnet, 'OUTGOING', 'HPNET')
            st.success(f"Đã nạp {c} văn bản đi HPNET (từ tổng số {raw} dòng trong file)!")
