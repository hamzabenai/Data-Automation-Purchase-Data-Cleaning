import streamlit as st
import google.generativeai as genai
import pandas as pd
import re
import time
from dotenv import load_dotenv
import os
from io import BytesIO

load_dotenv()
api_key = os.getenv('API_KEY')

# Streamlit app title
st.title("Data Cleaning and Mapping Tool")

# Function to load commune data
def load_material_data():
    commune_data = pd.read_excel(r'data/process_data.xlsx', sheet_name='communes')
    return commune_data

# Function to load input data
def load_input_data(uploaded_file):
    df = pd.read_excel(uploaded_file)
    return df

# Function to clean data
def cleaning_data(df):
    df = df.drop(columns=['status', 'EXPEDITION'])
    df = df[['الاسم و لقب', 'رقم الهاتف', 'الولاية', 'العنوان', 'produits', 'السعر', 'comment-3', 'comment-1', 'comment-2']]
    df['reference'] = df['produits']
    df.insert(0, 'reference', df.pop('reference'))
    df[['comment-1', 'comment-2', 'comment-3']] = df[['comment-1', 'comment-2', 'comment-3']].astype(str)
    df['remarque'] = df['comment-3'] + '+' + df['comment-1'] + '+' + df['comment-2']
    df = df.drop(columns=['comment-3', 'comment-1', 'comment-2'])
    df.rename(columns={'الاسم و لقب': 'nom et prenom du destinataire*', 'رقم الهاتف': 'telephone*', 'الولاية': 'wilaya de livraison', 'العنوان': 'adresse de livraison*', 'produits': 'produit (référence)*', 'السعر': 'montant du colis*'}, inplace=True)
    df['nom et prenom du destinataire*'].fillna('pas de nom', inplace=True)
    df['telephone 2'] = None
    df['code wilaya*'] = None
    df['commune de livraison*'] = None
    df['poids (kg)'] = None
    df['FRAGILE'] = None
    df['OUVRIR'] = None
    df['ECHANGE'] = None
    df['STOP DESK'] = None
    df['Lien map'] = None
    df = df[['reference', 'nom et prenom du destinataire*', 'telephone*', 'telephone 2', 'code wilaya*', 'wilaya de livraison', 'commune de livraison*', 'adresse de livraison*', 'produit (référence)*', 'poids (kg)', 'montant du colis*', 'remarque', 'FRAGILE', 'OUVRIR', 'ECHANGE', 'STOP DESK', 'Lien map']]
    df['telephone*'] = df['telephone*'].astype(str)
    df['telephone*'] = df['telephone*'].str.replace(' ', '')
    df['montant du colis*'] = df['montant du colis*'].replace('[^0-9.]', '', regex=True)
    df['montant du colis*'] = df['montant du colis*'].replace('', pd.NA)
    df['montant du colis*'] = pd.to_numeric(df['montant du colis*'], errors='coerce')
    df['montant du colis*'] = df['montant du colis*'].astype(int)    
    def format_algerian_phone(phone):
    # Remove any non-digit characters
        phone = ''.join(filter(str.isdigit, str(phone)))
        
        # Check if the phone number is valid
        if len(phone) == 9:
            # Add leading zero for landline numbers
            phone = '0' + phone
        elif len(phone) == 10:
            # Ensure it starts with 0
            if not phone.startswith('0'):
                return None  # Invalid format
        else:
            return None  # Invalid length
        
        # Validate Algerian phone number format
        if phone.startswith('0') and (len(phone) == 10 or len(phone) == 9):
            return phone
        else:
            return None  # Invalid format
    df['telephone*'] = df['telephone*'].apply(format_algerian_phone)
    return df


def load_model():
    genai.configure(api_key="AIzaSyCggDnTG__jpKsRNaMiclJDEGucy4PqobA")
    model = genai.GenerativeModel('gemini-2.0-flash')
    return model

def mapping_code_commune(commune_data, df, model):
    commune_names = commune_data['nom communes'].tolist()
    wilaya_info = {}
    cooldown_time = 5  

    progress_bar = st.progress(0)
    total_rows = len(df)
    
    for index, row in df.iterrows():
        wilaya = row['wilaya de livraison']
        address = row['adresse de livraison*']
        try:
            response_text = get_wilaya_info(wilaya, address, commune_names, model)
            code_wilaya, nom_commune = extract_info(response_text)
            
            wilaya_info[wilaya] = {
                "code wilaya": code_wilaya,
                "nom commune": nom_commune,
                "wilaya de livraison": wilaya,
                "adresse de livraison*": address
            }
            
            # Update progress bar
            progress = (index + 1) / total_rows
            progress_bar.progress(progress)
            
            time.sleep(cooldown_time)
        except Exception as e:
            print(f"Error processing {wilaya}: {e}")
            wilaya_info[wilaya] = {
                "code wilaya": None,
                "nom commune": None,
                "wilaya de livraison": wilaya,
                "adresse de livraison*": address
            }
    return wilaya_info

def get_wilaya_info(wilaya_name, address, commune_names, model):
    prompt = f'''For the wilaya: {wilaya_name} in Algeria and address: {address}, provide the 'code wilaya' and 'nom commune'.
    The 'nom commune' must be one of the following: {", ".join(commune_names)}.
    Use the following format:
    "code wilaya": "XX",
    "nom commune": "XXXXX"
    Ensure the response contains only the code wilaya as a two-digit number and the nom commune as a string from the provided list.'''
    response = model.generate_content(prompt)
    return response.text

def extract_info(response_text):
    code_wilaya_match = re.search(r'"code wilaya":\s*"(\d{2})"', response_text)
    nom_commune_match = re.search(r'"nom commune":\s*"([^"]+)"', response_text)
    
    code_wilaya = code_wilaya_match.group(1) if code_wilaya_match else None
    nom_commune = nom_commune_match.group(1) if nom_commune_match else None
    
    return code_wilaya, nom_commune

def assign_map_values(df, wilaya_info):
    df['code wilaya*'] = df['wilaya de livraison'].map(lambda x: wilaya_info[x]['code wilaya'])
    df['commune de livraison*'] = df['wilaya de livraison'].map(lambda x: wilaya_info[x]['nom commune'])
    return df

def main():
    try:
        # Check if xlsxwriter is installed
        import xlsxwriter
    except ImportError:
        st.error("The 'xlsxwriter' library is not installed. Please install it using `pip install xlsxwriter`.")
        return

    commune_data = load_material_data()
    st.write("Your input data should look like the following example:")
    raw = pd.read_excel(r'data/raw_data.xlsx').head()
    st.dataframe(raw)
    
    st.header("Download Template CSV File")
    st.write("If you don't have a file, you can download the template below:")
    example_df = pd.read_excel(r'data/raw_data_template.xlsx')
    csv = example_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Template CSV",
        data=csv,
        file_name="template.csv",
        mime="text/csv",
    )
    
    st.header('Upload your data')
    uploaded_file = st.file_uploader("Upload your raw data file (Excel)", type=["xlsx"])
    if uploaded_file is not None:
        df = load_input_data(uploaded_file)
        df = cleaning_data(df)

        model = load_model()

        with st.spinner("Mapping code wilaya and commune..."):
            wilaya_info = mapping_code_commune(commune_data, df, model)

        df = assign_map_values(df, wilaya_info)

        st.write("Cleaned Data:")
        st.dataframe(df)

        # Convert DataFrame to Excel in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Cleaned Data')
        output.seek(0)  # Reset the stream position to the beginning

        st.download_button(
            label="Download Cleaned Data as Excel",
            data=output,
            file_name="cleaned_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    main()