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

def clean_for_dedup(text):
    if not text or pd.isna(text): return ""
    text = str(text).lower()
    text = re.sub(r'(v/v\s*:?|về việc\s*:?)', '', text)
    # Remove all non-alphanumeric characters (keeping vietnamese characters is fine since \W might strip them depending on locale, 
    # but re in python3 supports unicode with \w. We just remove whitespace and punctuation)
    text = re.sub(r'[\s\.\,\-\_\:\;\'\"\(\)\[\]\{\}]', '', text)
    return text

def process_uploaded_file(file, doc_type, system_name):
    if file is not None:
        try:
            df = pd.read_excel(file, header=None)
            conn = get_connection()
            count = 0
            raw_count = 0
            
            # Xóa dữ liệu cũ của riêng Hệ thống này (VOFFICE hoặc HPNET) để tránh trùng lặp
            conn.execute("DELETE FROM documents WHERE type = ? AND content = ?", (doc_type, system_name))
            
            # Lấy danh sách văn bản đã có để tránh trùng lặp dựa vào trích yếu
            existing_docs = set()
            for r in conn.execute("SELECT document_no, summary FROM documents WHERE type = ?", (doc_type,)).fetchall():
                key = clean_for_dedup(r['summary'])
                if not key:
                    key = clean_for_dedup(r['document_no'])
                if key:
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
                        
                        key_to_check = clean_for_dedup(summary)
                        if not key_to_check:
                            key_to_check = clean_for_dedup(doc_number)
                            
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
                            
                            if key_to_check:
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

with st.form("upload_form"):
    col_up1, col_up2 = st.columns(2)

    with col_up1:
        st.info("📥 VĂN BẢN ĐẾN")
        file_in_voffice = st.file_uploader("Kéo thả file Văn bản đến - VOFFICE", type=["xlsx", "xls"], key="in_voffice")
        file_in_hpnet = st.file_uploader("Kéo thả file Văn bản đến - HPNET", type=["xlsx", "xls"], key="in_hpnet")

    with col_up2:
        st.info("📤 VĂN BẢN ĐI")
        file_out_voffice = st.file_uploader("Kéo thả file Văn bản đi - VOFFICE", type=["xlsx", "xls"], key="out_voffice")
        file_out_hpnet = st.file_uploader("Kéo thả file Văn bản đi - HPNET", type=["xlsx", "xls"], key="out_hpnet")
        
    submit_btn = st.form_submit_button("🚀 Cập nhật dữ liệu Upload")

if submit_btn:
    has_file = False
    if file_in_voffice:
        has_file = True
        with st.spinner("Đang xử lý VOFFICE (Đến)..."):
            c, raw = process_uploaded_file(file_in_voffice, 'INCOMING', 'VOFFICE')
            st.success(f"Đã nạp {c} văn bản đến VOFFICE (từ tổng số {raw} dòng trong file)!")
            
    if file_in_hpnet:
        has_file = True
        with st.spinner("Đang xử lý HPNET (Đến)..."):
            c, raw = process_uploaded_file(file_in_hpnet, 'INCOMING', 'HPNET')
            st.success(f"Đã nạp {c} văn bản đến HPNET (từ tổng số {raw} dòng trong file)!")
            
    if file_out_voffice:
        has_file = True
        with st.spinner("Đang xử lý VOFFICE (Đi)..."):
            c, raw = process_uploaded_file(file_out_voffice, 'OUTGOING', 'VOFFICE')
            st.success(f"Đã nạp {c} văn bản đi VOFFICE (từ tổng số {raw} dòng trong file)!")
            
    if file_out_hpnet:
        has_file = True
        with st.spinner("Đang xử lý HPNET (Đi)..."):
            c, raw = process_uploaded_file(file_out_hpnet, 'OUTGOING', 'HPNET')
            st.success(f"Đã nạp {c} văn bản đi HPNET (từ tổng số {raw} dòng trong file)!")
            
    if not has_file:
        st.warning("Vui lòng tải lên ít nhất một file Excel trước khi nhấn Cập nhật!")

st.markdown("---")
st.markdown("### 🗃️ Dữ liệu Voffice + Hpnet (Đã loại trừ trùng lặp)")

conn = get_connection()
try:
    incoming_docs = conn.execute("SELECT document_no as 'Ký hiệu', summary as 'Trích yếu', issued_date as 'Ngày ban hành', system_source as 'Nơi ban hành', content as 'Hệ thống' FROM documents WHERE type = 'INCOMING' ORDER BY created_at DESC").fetchall()
    outgoing_docs = conn.execute("SELECT document_no as 'Ký hiệu', summary as 'Trích yếu', issued_date as 'Ngày ban hành', system_source as 'Nơi ban hành', content as 'Hệ thống' FROM documents WHERE type = 'OUTGOING' ORDER BY created_at DESC").fetchall()
    
    t1, t2 = st.tabs(["📥 Văn bản đến Voffice+Hpnet", "📤 Văn bản đi Voffice+Hpnet"])
    
    with t1:
        if incoming_docs:
            df_in = pd.DataFrame([dict(row) for row in incoming_docs])
            df_in.insert(0, 'TT', range(1, 1 + len(df_in)))
            st.dataframe(df_in, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có dữ liệu Văn bản đến.")
            
    with t2:
        if outgoing_docs:
            df_out = pd.DataFrame([dict(row) for row in outgoing_docs])
            df_out.insert(0, 'TT', range(1, 1 + len(df_out)))
            st.dataframe(df_out, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có dữ liệu Văn bản đi.")

    st.markdown("---")
    st.markdown("### 📊 Phân tích dữ liệu Voffice+Hpnet")
    
    # 1. Trích yếu văn bản đi trùng/không trùng với văn bản đến
    inc_summaries = set([clean_for_dedup(r['Trích yếu']) for r in incoming_docs if clean_for_dedup(r['Trích yếu'])])
    
    trung_count = 0
    khong_trung_count = 0
    
    for r in outgoing_docs:
        key = clean_for_dedup(r['Trích yếu'])
        if key and key in inc_summaries:
            trung_count += 1
        else:
            khong_trung_count += 1

    col1, col2 = st.columns(2)
    with col1:
        st.success(f"✅ **Trích yếu văn bản ĐI TRÙNG với văn bản ĐẾN:** {trung_count}")
    with col2:
        st.warning(f"⚠️ **Trích yếu văn bản ĐI KHÔNG TRÙNG với văn bản ĐẾN:** {khong_trung_count}")
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    def count_doc_types(docs):
        keyword_mapping = {
            "quyết định": "Quyết định",
            "thông báo": "Thông báo",
            "báo cáo": "Báo cáo",
            "tờ trình": "Tờ trình",
            "kế hoạch": "Kế hoạch",
            "hướng dẫn": "Hướng dẫn",
            "chỉ thị": "Chỉ thị",
            "nghị quyết": "Nghị quyết",
            "giấy mời": "Giấy mời",
            "giấy triệu tập": "Giấy triệu tập",
            "chương trình": "Chương trình",
            "kết luận": "Kết luận",
            "quy định": "Quy định",
            "quy chế": "Quy chế"
        }
        
        doc_types_count = {}
        for r in docs:
            summary = str(r['Trích yếu']).strip() if r['Trích yếu'] else ""
            if not summary:
                continue
            summary_lower = summary.lower()
            if summary_lower.startswith("v/v"):
                summary_lower = summary_lower.replace("v/v", "", 1).replace(":", "", 1).strip()
            elif summary_lower.startswith("về việc"):
                summary_lower = summary_lower.replace("về việc", "", 1).replace(":", "", 1).strip()
                
            found_type = "Công văn (Các loại khác)"
            for kw, actual_type in keyword_mapping.items():
                if summary_lower.startswith(kw):
                    found_type = actual_type
                    break
            doc_types_count[found_type] = doc_types_count.get(found_type, 0) + 1
            
        return sorted(doc_types_count.items(), key=lambda x: x[1], reverse=True)

    st.markdown("#### 📑 Phân loại Nhóm Văn bản đi (Theo trích yếu)")
    sorted_all_types = count_doc_types(outgoing_docs)
    if sorted_all_types:
        num_cols = 4
        cols = st.columns(num_cols)
        for i, (dtype, count) in enumerate(sorted_all_types):
            with cols[i % num_cols]:
                st.metric(label=f"Số lượng {dtype}", value=count)
    else:
        st.info("Chưa có dữ liệu văn bản đi để phân tích.")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📑 Phân loại Nhóm Văn bản đến (Theo Trích yếu)")
    sorted_in_types = count_doc_types(incoming_docs)
    if sorted_in_types:
        num_cols = 4
        cols = st.columns(num_cols)
        for i, (dtype, count) in enumerate(sorted_in_types):
            with cols[i % num_cols]:
                st.metric(label=f"Số lượng {dtype}", value=count)
    else:
        st.info("Chưa có dữ liệu văn bản đến để phân tích.")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 🚨 NỢ ĐỌNG: Văn bản đến từ Sở, Ban, Ngành (Chưa có văn bản đi)")
    
    out_summaries = set([clean_for_dedup(r['Trích yếu']) for r in outgoing_docs if clean_for_dedup(r['Trích yếu'])])
    
    so_ban_nganh_docs = []
    chu_tich_docs = []
    
    for r in incoming_docs:
        key = clean_for_dedup(r['Trích yếu'])
        if key and key not in out_summaries:
            source = str(r['Nơi ban hành']).lower() if r['Nơi ban hành'] else ""
            if "chủ tịch" in source:
                chu_tich_docs.append(r)
            else:
                so_ban_nganh_docs.append(r)
                
    sorted_sbn_types = count_doc_types(so_ban_nganh_docs)
    if sorted_sbn_types:
        num_cols = 4
        cols = st.columns(num_cols)
        for i, (dtype, count) in enumerate(sorted_sbn_types):
            with cols[i % num_cols]:
                st.metric(label=f"Số lượng {dtype}", value=count)
                
        # Hiển thị danh sách chi tiết
        st.markdown("**Danh sách chi tiết văn bản Sở, Ban, Ngành nợ đọng:**")
        df_sbn = pd.DataFrame([dict(r) for r in so_ban_nganh_docs])
        df_sbn.insert(0, 'TT', range(1, 1 + len(df_sbn)))
        st.dataframe(df_sbn, use_container_width=True, hide_index=True)
    else:
        st.success("Tuyệt vời! Không có văn bản nợ đọng từ các Sở, ban, ngành.")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 🚨 NỢ ĐỌNG: Văn bản đến của Chủ tịch Công ty (Chưa có văn bản đi)")
    
    sorted_ct_types = count_doc_types(chu_tich_docs)
    if sorted_ct_types:
        num_cols = 4
        cols = st.columns(num_cols)
        for i, (dtype, count) in enumerate(sorted_ct_types):
            with cols[i % num_cols]:
                st.metric(label=f"Số lượng {dtype}", value=count)
                
        # Hiển thị danh sách chi tiết
        st.markdown("**Danh sách chi tiết văn bản của Chủ tịch Công ty nợ đọng:**")
        df_ct = pd.DataFrame([dict(r) for r in chu_tich_docs])
        df_ct.insert(0, 'TT', range(1, 1 + len(df_ct)))
        st.dataframe(df_ct, use_container_width=True, hide_index=True)
    else:
        st.success("Tuyệt vời! Không có văn bản nợ đọng từ Chủ tịch Công ty.")
        
finally:
    conn.close()
