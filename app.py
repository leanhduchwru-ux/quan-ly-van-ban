import streamlit as st
import pandas as pd
from database import get_connection
import uuid
import datetime
import io
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
import plotly.express as px

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

def match_documents(system_name=None):
    conn = get_connection()
    try:
        if system_name:
            incoming_docs = conn.execute("SELECT * FROM documents WHERE type = 'INCOMING' AND content = ?", (system_name,)).fetchall()
            outgoing_docs = conn.execute("SELECT * FROM documents WHERE type = 'OUTGOING' AND content = ?", (system_name,)).fetchall()
        else:
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

st.markdown("### 📥 Nạp dữ liệu từ File Excel")
st.markdown("Vui lòng tải lên file danh sách xuất ra từ hệ thống. File cần có các cột chứa chữ **'Ký hiệu'** và **'Trích yếu'**.")

col_up1, col_up2 = st.columns(2)

def process_uploaded_file(file, doc_type, system_name):
    if file is not None:
        try:
            df = pd.read_excel(file, header=None)
            conn = get_connection()
            
            # Xóa dữ liệu cũ của riêng Hệ thống này (VOFFICE hoặc HPNET) để tránh trùng lặp
            # Lưu ý: Cột content được dùng để lưu tên hệ thống (VOFFICE/HPNET)
            conn.execute("DELETE FROM documents WHERE type = ? AND content = ?", (doc_type, system_name))
            
            # Lấy danh sách văn bản đã có để tránh trùng lặp
            existing_docs = {row['document_no'] for row in conn.execute("SELECT document_no FROM documents WHERE type = ?", (doc_type,)).fetchall()}
            
            count = 0
            doc_col = -1
            summary_col = -1
            assignee_col = -1
            date_col = -1
            agency_col = -1
            
            import re
            
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
                            # Loại bỏ "00:00:00" nếu pandas ép kiểu nhầm thành string có giờ
                            doc_date = doc_date.replace("00:00:00", "").strip()
                            
                    agency = str(row[agency_col]).strip() if agency_col != -1 and pd.notna(row[agency_col]) else ""
                    
                    if doc_number and doc_number.lower() not in ['nan', 'none', '']:
                        if doc_number not in existing_docs:
                            doc_id = str(uuid.uuid4())
                            # Lưu tên hệ thống vào cột content, lưu cơ quan vào cột system_source
                            conn.execute("INSERT INTO documents (id, type, document_no, issued_date, system_source, summary, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                         (doc_id, doc_type, doc_number, doc_date, agency, summary, system_name))
                            
                            # Xử lý bóc tách Người xử lý (Lấy chính xác người liền sau Trương Mạnh Tiến)
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
                                    # Lấy người liền sau Trương Mạnh Tiến
                                    assignee = parts[tm_index + 1]
                                elif tm_index == -1 and parts:
                                    # Không có Trương Mạnh Tiến, bỏ qua từ khóa 'Lưu'
                                    filtered = [p for p in parts if p.lower() not in ['lưu', 'lưu trữ', 'văn thư', 'vt']]
                                    assignee = filtered[0] if filtered else parts[0]
                                else:
                                    assignee = "Trương Mạnh Tiến"
                                
                                # Xóa bớt chữ thừa như "(Xử lý chính)", "(Phối hợp)" để tên gọn gàng
                                assignee = re.sub(r'\(.*?\)', '', assignee).strip()
                                
                                conn.execute("INSERT INTO tasks (id, document_id, assignee, status) VALUES (?, ?, ?, ?)",
                                             (str(uuid.uuid4()), doc_id, assignee, 'Đang xử lý'))
                            
                            existing_docs.add(doc_number)
                            count += 1
            
            if doc_col == -1 or summary_col == -1:
                st.error("File không đúng định dạng cấu trúc, vui lòng kiểm tra lại cột Ký hiệu hoặc Trích yếu")
                conn.close()
                return 0

            conn.commit()
            conn.close()
            return count
        except Exception as e:
            st.error(f"Lỗi đọc file: {e}")
            return 0
    return 0

with col_up1:
    st.info("📥 VĂN BẢN ĐẾN")
    file_in_voffice = st.file_uploader("Kéo thả file Văn bản đến - VOFFICE", type=["xlsx", "xls"], key="in_voffice")
    if file_in_voffice:
        with st.spinner("Đang xử lý VOFFICE..."):
            c = process_uploaded_file(file_in_voffice, 'INCOMING', 'VOFFICE')
            st.success(f"Đã nạp {c} văn bản đến VOFFICE!")
            
    file_in_hpnet = st.file_uploader("Kéo thả file Văn bản đến - HPNET", type=["xlsx", "xls"], key="in_hpnet")
    if file_in_hpnet:
        with st.spinner("Đang xử lý HPNET..."):
            c = process_uploaded_file(file_in_hpnet, 'INCOMING', 'HPNET')
            st.success(f"Đã nạp {c} văn bản đến HPNET!")

with col_up2:
    st.info("📤 VĂN BẢN ĐI")
    file_out_voffice = st.file_uploader("Kéo thả file Văn bản đi - VOFFICE", type=["xlsx", "xls"], key="out_voffice")
    if file_out_voffice:
        with st.spinner("Đang xử lý VOFFICE..."):
            c = process_uploaded_file(file_out_voffice, 'OUTGOING', 'VOFFICE')
            st.success(f"Đã nạp {c} văn bản đi VOFFICE!")
            
    file_out_hpnet = st.file_uploader("Kéo thả file Văn bản đi - HPNET", type=["xlsx", "xls"], key="out_hpnet")
    if file_out_hpnet:
        with st.spinner("Đang xử lý HPNET..."):
            c = process_uploaded_file(file_out_hpnet, 'OUTGOING', 'HPNET')
            st.success(f"Đã nạp {c} văn bản đi HPNET!")

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("🔄 Chạy Đối Chiếu Tự Động VOFFICE", type="primary", use_container_width=True):
        with st.spinner("Đang phân tích và đối chiếu VOFFICE..."):
            updated = match_documents('VOFFICE')
            st.success(f"Đã đối chiếu thành công {updated} văn bản VOFFICE! Vui lòng xem kết quả bên dưới.")

with col_btn2:
    if st.button("🔄 Chạy Đối Chiếu Tự Động HPNET", type="primary", use_container_width=True):
        with st.spinner("Đang phân tích và đối chiếu HPNET..."):
            updated = match_documents('HPNET')
            st.success(f"Đã đối chiếu thành công {updated} văn bản HPNET! Vui lòng xem kết quả bên dưới.")


st.markdown("---")

conn = get_connection()
relations = conn.execute('''
    SELECT 
        r.match_status,
        i.document_no as inc_doc,
        i.issued_date as inc_date,
        i.system_source as inc_agency,
        i.summary as inc_summary,
        i.content as system_name,
        o.document_no as out_doc,
        o.issued_date as out_date,
        o.system_source as out_agency,
        i.id as inc_id
    FROM document_relations r
    JOIN documents i ON r.incoming_id = i.id
    LEFT JOIN documents o ON r.outgoing_id = o.id
''').fetchall()

data_voffice = []
data_hpnet = []
stats_voffice = {"Đang nhận việc": 0, "Chưa có văn bản trả lời": 0, "Có văn bản đi": 0}
stats_hpnet = {"Đang nhận việc": 0, "Chưa có văn bản trả lời": 0, "Có văn bản đi": 0}

if len(relations) == 0:
    st.info("Cơ sở dữ liệu đang trống. Vui lòng tải dữ liệu từ file Excel lên.")
else:
    for rel in relations:
        sys_name = rel['system_name']
        status = rel['match_status']
        
        tasks = conn.execute("SELECT assignee FROM tasks WHERE document_id = ?", (rel['inc_id'],)).fetchall()
        assignees = ", ".join([t['assignee'] for t in tasks if t['assignee']]) if tasks else ""
        
        display_status = status
        if status == 'Đang nhận việc':
            display_status = '🟡 Đang nhận việc'
        elif status == 'Chưa có văn bản trả lời':
            display_status = '🔴 Chưa có trả lời'
        elif status == 'Có văn bản đi':
            display_status = '🟢 Có văn bản đi'
            
        row_data = {
            "Văn bản đến": rel['inc_doc'],
            "ngày đến": rel['inc_date'] if rel['inc_date'] else "",
            "Nơi gửi đến": rel['inc_agency'] if rel['inc_agency'] else "",
            "Trích yếu": rel['inc_summary'],
            "Người xử lý": assignees,
            "VB đi": rel['out_doc'] if rel['out_doc'] else "",
            "Ngày gửi đi": rel['out_date'] if rel['out_date'] else "",
            "Nơi gửi đi": rel['out_agency'] if rel['out_agency'] else "",
            "Trạng thái": display_status
        }
        
        if sys_name == 'VOFFICE':
            stats_voffice[status] = stats_voffice.get(status, 0) + 1
            data_voffice.append(row_data)
        elif sys_name == 'HPNET':
            stats_hpnet[status] = stats_hpnet.get(status, 0) + 1
            data_hpnet.append(row_data)
        else:
            # Dự phòng nếu không có tên hệ thống
            stats_hpnet[status] = stats_hpnet.get(status, 0) + 1
            data_hpnet.append(row_data)

conn.close()

def color_status(val):
    if 'Đang nhận việc' in str(val): return 'color: #eab308; font-weight: bold;'
    elif 'Chưa có' in str(val): return 'color: #ef4444; font-weight: bold;'
    elif 'Có văn bản đi' in str(val): return 'color: #22c55e; font-weight: bold;'
    return ''

def generate_excel_report(df, system_name):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Báo Cáo"
    
    # Quốc hiệu tiêu ngữ
    ws.merge_cells('A1:J1')
    ws['A1'] = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
    ws['A1'].font = Font(name='Times New Roman', size=13, bold=True)
    ws['A1'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:J2')
    ws['A2'] = "Độc lập - Tự do - Hạnh phúc"
    ws['A2'].font = Font(name='Times New Roman', size=14, bold=True, underline='single')
    ws['A2'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A4:J4')
    ws['A4'] = f"BẢNG KÊ ĐỐI CHIẾU VĂN BẢN ĐẾN - {system_name}"
    ws['A4'].font = Font(name='Times New Roman', size=14, bold=True)
    ws['A4'].alignment = Alignment(horizontal='center')
    
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    header_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    
    # Headers
    headers = list(df.columns)
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=6, column=col_num, value=header)
        cell.font = Font(name='Times New Roman', size=12, bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin_border
        cell.fill = header_fill
        
    # Data
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=False), 7):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.font = Font(name='Times New Roman', size=12)
            cell.border = thin_border
            
            # Wrap text for Trích yếu (cột 5)
            if c_idx == 5:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
            else:
                cell.alignment = Alignment(vertical='top')
                
            # Color status (cột 10)
            if c_idx == 10 and value:
                if 'Đang nhận việc' in str(value):
                    cell.font = Font(name='Times New Roman', size=12, color='CA8A04', bold=True)
                elif 'Chưa có' in str(value):
                    cell.font = Font(name='Times New Roman', size=12, color='DC2626', bold=True)
                elif 'Có văn bản đi' in str(value):
                    cell.font = Font(name='Times New Roman', size=12, color='16A34A', bold=True)

    # Column widths
    widths = [5, 15, 12, 20, 40, 15, 15, 12, 20, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

def render_table(title, data_list, stats, system_name):
    st.markdown(f"### 📋 {title}")
    
    df = pd.DataFrame(data_list)
    if df.empty:
        st.info("Chưa có dữ liệu.")
        return

    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        c1, c2, c3 = st.columns(3)
        c1.metric("🟡 Đang nhận việc", stats.get("Đang nhận việc", 0))
        c2.metric("🔴 Chưa có VB trả lời", stats.get("Chưa có văn bản trả lời", 0))
        c3.metric("🟢 Có văn bản đi", stats.get("Có văn bản đi", 0))

        # Bộ lọc
        f1, f2 = st.columns(2)
        with f1:
            status_options = ["Tất cả"] + list(df['Trạng thái'].unique())
            selected_status = st.selectbox(f"Lọc Trạng thái ({system_name})", status_options, key=f"status_{system_name}")
        with f2:
            assignees_set = set()
            for a in df['Người xử lý']:
                if a:
                    assignees_set.update([x.strip() for x in str(a).split(',') if x.strip()])
            assignee_options = ["Tất cả"] + sorted(list(assignees_set))
            selected_assignee = st.selectbox(f"Lọc Người xử lý ({system_name})", assignee_options, key=f"assignee_{system_name}")

    with col_right:
        chart_data = pd.DataFrame({
            'Trạng thái': ['🟡 Đang nhận việc', '🔴 Chưa có trả lời', '🟢 Có văn bản đi'],
            'Số lượng': [stats.get("Đang nhận việc", 0), stats.get("Chưa có văn bản trả lời", 0), stats.get("Có văn bản đi", 0)]
        })
        # Lọc bỏ các trạng thái = 0 để biểu đồ đẹp hơn
        chart_data = chart_data[chart_data['Số lượng'] > 0]
        if not chart_data.empty:
            fig = px.pie(chart_data, values='Số lượng', names='Trạng thái', hole=0.5, 
                         color='Trạng thái',
                         color_discrete_map={
                             '🟡 Đang nhận việc': '#eab308', 
                             '🔴 Chưa có trả lời': '#ef4444', 
                             '🟢 Có văn bản đi': '#22c55e'
                         })
            fig.update_layout(margin=dict(t=20, b=20, l=0, r=0), showlegend=True, legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, use_container_width=True)

    # Áp dụng bộ lọc
    filtered_df = df.copy()
    if selected_status != "Tất cả":
        filtered_df = filtered_df[filtered_df['Trạng thái'] == selected_status]
    if selected_assignee != "Tất cả":
        filtered_df = filtered_df[filtered_df['Người xử lý'].str.contains(selected_assignee, na=False)]

    if not filtered_df.empty:
        filtered_df.insert(0, 'TT', range(1, 1 + len(filtered_df)))
        st.dataframe(
            filtered_df.style.map(color_status, subset=['Trạng thái']),
            use_container_width=True, 
            hide_index=True,
            column_order=["TT", "Văn bản đến", "ngày đến", "Nơi gửi đến", "Trích yếu", "Người xử lý", "VB đi", "Ngày gửi đi", "Nơi gửi đi", "Trạng thái"],
            column_config={
                "TT": st.column_config.NumberColumn("TT", width="small"),
                "Văn bản đến": st.column_config.TextColumn("Văn bản đến", width="medium"),
                "ngày đến": st.column_config.TextColumn("ngày đến", width="small"),
                "Nơi gửi đến": st.column_config.TextColumn("Nơi gửi đến", width="medium"),
                "Trích yếu": st.column_config.TextColumn("Trích yếu", width="large"),
                "Người xử lý": st.column_config.TextColumn("Người xử lý", width="medium"),
                "VB đi": st.column_config.TextColumn("VB đi", width="medium"),
                "Ngày gửi đi": st.column_config.TextColumn("Ngày gửi đi", width="small"),
                "Nơi gửi đi": st.column_config.TextColumn("Nơi gửi đi", width="medium"),
                "Trạng thái": st.column_config.TextColumn("Trạng thái (Hệ thống)", width="medium")
            }
        )
        
        excel_data = generate_excel_report(filtered_df, system_name)
        st.download_button(
            label=f"📥 Tải Xuống Báo Cáo Excel ({system_name})",
            data=excel_data,
            file_name=f"BaoCao_DoiChieu_{system_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_{system_name}"
        )
    else:
        st.warning("Không tìm thấy dữ liệu phù hợp với bộ lọc.")

render_table("Bảng Thống Kê Đối Chiếu VB đến VOFFICE", data_voffice, stats_voffice, "VOFFICE")
st.markdown("---")
render_table("Bảng Thống Kê Đối Chiếu VB đến HPNET", data_hpnet, stats_hpnet, "HPNET")
