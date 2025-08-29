"""
PDF Export Demo - Streamlit Application

This is a standalone demo showing how to use the PDF export functionality.
Run this file with: streamlit run pdf_demo.py
"""

import streamlit as st
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from modules.pdf_export import streamlit_pdf_export_demo

def main():
    """Main demo application"""
    st.set_page_config(
        page_title="PDF Export Demo",
        page_icon="📄",
        layout="wide"
    )
    
    st.title("📄 Quiz PDF Export Demo")
    st.markdown("---")
    
    # Basic demo
    streamlit_pdf_export_demo()
    
    st.markdown("---")
    
    # Advanced demo with custom questions
    st.subheader("🔧 Custom Questions Demo")
    
    # Allow users to input their own questions
    with st.expander("Add Custom Questions"):
        question_number = st.text_input("Question Number", value="DEMO1")
        question_text = st.text_area("Question Text", 
                                   value="What is the most important factor in maintaining oral health?")
        
        # Choices input
        choice_a = st.text_input("Choice A", value="Regular brushing")
        choice_b = st.text_input("Choice B", value="Professional cleaning")
        choice_c = st.text_input("Choice C", value="Fluoride treatment")
        choice_d = st.text_input("Choice D", value="All of the above")
        
        correct_answer = st.selectbox("Correct Answer", ["A", "B", "C", "D"])
        
        if st.button("Add Question"):
            if "custom_questions" not in st.session_state:
                st.session_state.custom_questions = []
            
            new_question = {
                "number": question_number,
                "question": question_text,
                "choices": [
                    {"text": choice_a},
                    {"text": choice_b},
                    {"text": choice_c},
                    {"text": choice_d}
                ],
                "answer": correct_answer
            }
            
            st.session_state.custom_questions.append(new_question)
            st.success(f"Question {question_number} added!")
    
    # Display and export custom questions
    if "custom_questions" in st.session_state and st.session_state.custom_questions:
        st.subheader("Your Custom Questions")
        
        for i, q in enumerate(st.session_state.custom_questions):
            with st.expander(f"Question {i+1}: {q['number']}"):
                st.write(f"**Question:** {q['question']}")
                for j, choice in enumerate(q['choices']):
                    st.write(f"{chr(65+j)}) {choice['text']}")
                st.write(f"**Answer:** {q['answer']}")
        
        # Export custom questions
        if st.button("Generate PDF from Custom Questions", type="primary"):
            with st.spinner("Generating PDF from custom questions..."):
                from modules.pdf_export import QuizPDFExporter
                
                exporter = QuizPDFExporter()
                pdf_bytes, error_msg = exporter.export_questions_to_pdf(st.session_state.custom_questions)
                
                if pdf_bytes:
                    st.success("Custom PDF generated successfully!")
                    
                    # Create download button
                    import base64
                    b64_pdf = base64.b64encode(pdf_bytes).decode()
                    
                    href = f'''
                    <a href="data:application/pdf;base64,{b64_pdf}" 
                       download="custom_questions.pdf"
                       style="display: inline-block; padding: 0.5rem 1rem; 
                              color: white; background-color: #ff4b4b; border: none; 
                              border-radius: 0.25rem; text-decoration: none; 
                              font-weight: 600;">
                        📥 Download Custom PDF
                    </a>
                    '''
                    
                    st.markdown(href, unsafe_allow_html=True)
                else:
                    st.error(f"Failed to generate PDF: {error_msg}")
        
        # Clear questions button
        if st.button("Clear All Questions"):
            st.session_state.custom_questions = []
            st.rerun()
    
    # Technical information
    st.markdown("---")
    st.subheader("🔧 Technical Requirements")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Required Software:**
        - uplatex (Japanese LaTeX)
        - dvipdfmx (DVI to PDF converter)
        - Python packages: requests, streamlit
        """)
    
    with col2:
        st.markdown("""
        **Features:**
        - LaTeX special character escaping
        - Image support (local files and URLs)
        - tcolorbox styling for questions
        - Automatic fallback to simple format
        """)
    
    # Check requirements
    st.subheader("📋 System Check")
    
    import subprocess
    required_commands = ['uplatex', 'dvipdfmx']
    
    for cmd in required_commands:
        try:
            result = subprocess.run([cmd, '--version'], capture_output=True, check=True)
            st.success(f"✅ {cmd} is available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            st.error(f"❌ {cmd} is not available")


if __name__ == "__main__":
    main()
