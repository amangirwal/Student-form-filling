import streamlit as st
import fitz  
from PIL import Image
from pyzbar.pyzbar import decode
import io
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from sqlalchemy.orm import Session
from database import Student, get_db
import os


def extract_text_from_pdf(pdf_bytes):
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        text += page.get_text()
    return text

def extract_qr_codes_from_pdf(pdf_bytes):
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    qr_codes = []
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes()))
        qr_codes_page = decode(img)
        for qr in qr_codes_page:
            qr_codes.append(qr.data.decode('utf-8'))
    return qr_codes

def extract_name_and_scores(text):
    lines = text.split('\n')
    name = None
    marks = None
    assignment_score = None
    proctored_score = None
    uppercase_pattern = re.compile(r'\b[A-Z][A-Z\s]+\b')
    for i, line in enumerate(lines):
        if uppercase_pattern.match(line.strip()) and not re.search(r'\d+', line):
            name = line.strip()
        if i == 9:
            marks = line.strip()
        if i == 7:
            assignment_score = line.strip().split('/')[0].strip()
        if i == 8:
            proctored_score = line.strip().split('/')[0].strip()
    return name, marks, assignment_score, proctored_score

def extract_pdf_link_from_page(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        link = soup.find('a', string='Course Certificate')
        if link and link.get('href'):
            pdf_url = link['href']
            if not pdf_url.startswith('http'):
                pdf_url = requests.compat.urljoin(url, pdf_url)
            return pdf_url
        else:
            st.error(f"No 'Course Certificate' link found at {url}")
    except requests.RequestException as e:
        st.error(f"Error accessing URL {url}: {e}")
    return None

def download_pdf(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return io.BytesIO(response.content)
    except requests.RequestException as e:
        st.error(f"Error downloading PDF from {url}: {e}")
        return None

def extract_link(pdf_bytes):
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    found_url = None
    url_prefix = "https://internalapp.nptel.ac.in/"
    for page_number in range(len(document)):
        page = document.load_page(page_number)
        links = page.get_links()
        
        for link in links:
            uri = link.get("uri", None)
            if uri and uri.startswith(url_prefix):
                found_url = uri
                break  # Exit the loop once the first matching URL is found
    
        if found_url:
            return found_url
    
    return None

def process_pdf(pdf_bytes):
    text = extract_text_from_pdf(pdf_bytes)
    qr_codes = extract_qr_codes_from_pdf(pdf_bytes)
    original_name, original_marks, assignment_score, proctored_score = extract_name_and_scores(text)
    
    # Check if there are QR codes or if we need to use the extracted link
    if qr_codes:
        verification_results = []
        for qr in qr_codes:
            unique_id = qr.split('/')[-1]
            final_url = f"https://archive.nptel.ac.in/noc/Ecertificate/?q={unique_id}"
            extracted_pdf_link = extract_pdf_link_from_page(final_url)
            if extracted_pdf_link:
                fetched_pdf = download_pdf(extracted_pdf_link)
                if fetched_pdf:
                    fetched_pdf_text = extract_text_from_pdf(fetched_pdf)
                    fetched_name, fetched_marks, _, _ = extract_name_and_scores(fetched_pdf_text)
                    status = 'Verified' if (original_name == fetched_name and original_marks == fetched_marks) else 'Not Verified'
                    verification_results.append({
                        'link': qr,
                        'pdf_link': extracted_pdf_link,
                        'is_fetched': True,
                        'status': status
                    })
                else:
                    verification_results.append({
                        'link': qr,
                        'pdf_link': extracted_pdf_link,
                        'is_fetched': False,
                        'status': 'Not Verified'
                    })
            else:
                verification_results.append({
                    'link': qr,
                    'pdf_link': None,
                    'is_fetched': False,
                    'status': 'Not Verified'
                })
    else:
        # No QR codes found, use extracted link
        extracted_pdf_link = extract_link(pdf_bytes)
        verification_results = []
        if extracted_pdf_link:
            fetched_pdf = download_pdf(extracted_pdf_link)
            if fetched_pdf:
                fetched_pdf_text = extract_text_from_pdf(fetched_pdf)
                fetched_name, fetched_marks, _, _ = extract_name_and_scores(fetched_pdf_text)
                status = 'Verified' if (original_name == fetched_name and original_marks == fetched_marks) else 'Not Verified'
                verification_results.append({
                    'link': None,
                    'pdf_link': extracted_pdf_link,
                    'is_fetched': True,
                    'status': status
                })
            else:
                verification_results.append({
                    'link': None,
                    'pdf_link': extracted_pdf_link,
                    'is_fetched': False,
                    'status': 'Not Verified'
                })
        else:
            verification_results.append({
                'link': None,
                'pdf_link': None,
                'is_fetched': False,
                'status': 'Not Verified'
            })

    return {
        'name': original_name,
        'marks': original_marks,
        'assignment_score': assignment_score,
        'proctored_score': proctored_score,
        'verification_results': verification_results,
        'pdf_link': extracted_pdf_link if extracted_pdf_link else None
    }

def process_certificates(uploaded_files):
    results_list = []
    my_bar = st.progress(0)  # Progress bar
    total_files = len(uploaded_files)
    for i, uploaded_file in enumerate(uploaded_files):
        file_bytes = uploaded_file.read()
        results = process_pdf(file_bytes)
        results_list.append({
            'Filename': uploaded_file.name,
            'Name': results['name'],
            'Assignment Score (out of 25)': results['assignment_score'],
            'Proctored Exam Score (out of 75)': results['proctored_score'],
            'Marks (%)': results['marks'],
            'Status': any(result['status'] == 'Verified' for result in results['verification_results']),
            'links for pdf': results['pdf_link']
        })
        my_bar.progress((i + 1) / total_files)

    df = pd.DataFrame(results_list)
    df['Status'] = df['Status'].apply(lambda x: 'Verified' if x else 'Not Verified')
    df = df.sort_values(by='Status', ascending=False) 
    return df




# Streamlit Form for Student Information
def student_form():
    st.title("Student Details Form")
    st.write("please enter every details carefully and give correct data")
    with st.form("student_form"):
        student_name = st.text_input("Full Name")
        student_email = st.text_input("Email")
        student_id = st.text_input("Enrollemet NO.")
        student_year = st.text_input("Year")
        certificate_url = st.text_input("NPTEL Certificate URL (Optional)")
        certificate_file = st.file_uploader("Or Upload Certificate PDF (Optional)", type=['pdf'])
        
        submitted = st.form_submit_button("Submit")

        if submitted:
            if student_name and student_email and student_id:
                certificate_file_name = None
                if certificate_file:
                    certificate_file_name = certificate_file.name
                    save_certificate_file(certificate_file)
                
                # Save data to the database
                save_student_data(student_name, student_email, student_id, certificate_url, certificate_file_name)
                st.success("Student data submitted successfully!")
            else:
                st.error("Please fill in all required fields.")
                
def save_certificate_file(certificate_file):
    if not os.path.exists("certificates"):
        os.makedirs("certificates")
    with open(f"certificates/{certificate_file.name}", "wb") as f:
        f.write(certificate_file.getbuffer())

def save_student_data(name, email, course_id, certificate_url=None, certificate_file_name=None):
    db = next(get_db())
    student = Student(
        name=name,
        email=email,
        student_id=course_id,
        certificate_url=certificate_url,
        certificate_file_name=certificate_file_name
    )
    db.add(student)
    db.commit()

def show_students():
    db = next(get_db())
    students = db.query(Student).all()

    st.title("Student Database")
    if students:
        for student in students:
            st.write(f"Name: {student.name}, Email: {student.email},  Student ID: {student.student_id}")
            st.write(f"Certificate URL: {student.certificate_url}")
            st.write(f"Uploaded Certificate: {student.certificate_file_name}")
            st.write("---")
    else:
        st.write("No students found.")

# Streamlit interface
page = st.sidebar.selectbox("Select Page", ["Student Form", "View Students", "Verify Students"])


if page == "Student Form":
    student_form()

elif page == "View Students":
    show_students()
    
elif page == "Verify Students":
    uploaded_files = "certificates"
    # uploaded_files = [os.path.join(certificates_folder, f) for f in os.listdir(certificates_folder) if f.endswith('.pdf')]
    verify = st.button("Verify")
    
    if verify:
        st.write("🔄 Processing...")
        results_df = process_certificates(uploaded_files)
        st.success("✔️ Processing completed!")
        st.write(results_df)
