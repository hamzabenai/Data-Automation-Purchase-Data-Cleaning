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
    df = df[(df['EXPEDITION'] == 'expidie') | (df['status'] == 'confirmer')]
    df = df.drop(columns=['status', 'EXPEDITION'])
    df = df[['الاسم و لقب', 'رقم الهاتف', 'الولاية', 'العنوان', 'produits', 'السعر', 'comment-3', 'comment-1', 'comment-2']]
    df['reference commande'] = df['produits']
    df.insert(0, 'reference commande', df.pop('reference commande'))
    df[['comment-1', 'comment-2', 'comment-3']] = df[['comment-1', 'comment-2', 'comment-3']].astype(str).fillna(' ')
    df['remarque'] = df['comment-3'] + '+' + df['comment-1'] + '+' + df['comment-2']
    df = df.drop(columns=['comment-3', 'comment-1', 'comment-2'])
    df.rename(columns={'الاسم و لقب': 'nom et prenom du destinataire*', 'رقم الهاتف': 'telephone*', 'الولاية': 'wilaya de livraison', 'العنوان': 'adresse de livraison*', 'produits': 'produit*', 'السعر': 'montant du colis*'}, inplace=True)
    df['nom et prenom du destinataire*'].fillna('pas de nom', inplace=True)
    df['adresse de livraison*'].fillna(df['wilaya de livraison'], inplace=True)
    df['telephone 2'] = None
    df['code wilaya*'] = None
    df['commune de livraison*'] = None
    df['poids (kg)'] = None
    df['FRAGILE\n( si oui mettez OUI sinon laissez vide )'] = None
    df['OUVRIR\n( si oui mettez OUI sinon laissez vide )'] = None
    df['ECHANGE\n( si oui mettez OUI sinon laissez vide )'] = None
    df['PICK UP\n( si oui mettez OUI sinon laissez vide )'] = None
    df['RECOUVREMENT\n( si oui mettez OUI sinon laissez vide )'] = None
    df['STOP DESK\n( si oui mettez OUI sinon laissez vide )'] = None
    df['Lien map'] = None
    df = df[['reference commande', 'nom et prenom du destinataire*', 'telephone*', 'telephone 2', 'code wilaya*', 'wilaya de livraison', 'commune de livraison*', 'adresse de livraison*', 'produit*', 'poids (kg)', 'montant du colis*', 'remarque', 'FRAGILE\n( si oui mettez OUI sinon laissez vide )', 'OUVRIR\n( si oui mettez OUI sinon laissez vide )', 'ECHANGE\n( si oui mettez OUI sinon laissez vide )','PICK UP\n( si oui mettez OUI sinon laissez vide )','RECOUVREMENT\n( si oui mettez OUI sinon laissez vide )','STOP DESK\n( si oui mettez OUI sinon laissez vide )', 'Lien map']]
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
def standardize_text(text):
    if pd.isna(text) or text.strip() == "":
        return ""
    return text.strip().capitalize()
def get_wilaya_info(wilaya_name, address, commune_names, model):
    # Standardize wilaya_name and address
    wilaya_name = standardize_text(wilaya_name)
    address = standardize_text(address)
    
    prompt = f'''
    Task: Extract the Algerian Wilaya code and Commune name from order details.

    you are a assistent that is aware of the algeria's geogriphic location
    Given the following order information, please try to find or identify the wilaya code and the commune name.

    Order Information:
    - Wilaya de livraison: {wilaya_name}
    - Commune de livraison: it's up to you to find it
    - Adresse de livraison: {address}
    - code wilaya: it's up to you to find it 
    
    Instructions:
    - the 'Commune de livraison' name must be in english and the 'code wilaya' must be a number.
    1. If the 'Existing Wilaya Code' is provided, use it.
    2. If the 'Commune de livraison' is provided, use it.
    3. If either the Wilaya Code or Commune is missing, use the 'Wilaya de livraison' and 'Adresse de livraison' to find the correct values.
    4. if you couldn't identify the wilaya code or the commune name, try to read it in arabic and find the corresponding wilaya code and commune name.
    5. if you coudn't find the Commune de livraison return the {wilaya_name}

    Use the following format:
    "code wilaya": "XX",
    "nom commune": "XXXXXXXXXXXXX"
    '''
    
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
    df['code wilaya*'] = pd.to_numeric(df['code wilaya*'], errors='coerce')
    return df

# Initialize session state
if 'df_processed' not in st.session_state:
    st.session_state.df_processed = None

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
    
    st.header("Download Template Excel File")
    st.write("If you don't have a file, you can download the template below:")

    # Load the template Excel file
    example_df = pd.read_excel(r'data/raw_data_template.xlsx')

    # Create an in-memory BytesIO object to store the Excel file
    output = BytesIO()

    # Save the DataFrame to the BytesIO object as an Excel file
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        example_df.to_excel(writer, index=False, sheet_name='Template')

    # Seek to the beginning of the stream
    output.seek(0)

    # Provide a download button for the Excel file
    st.download_button(
        label="Download Template Excel",
        data=output,
        file_name="template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.header('Upload your data')
    uploaded_file = st.file_uploader("Upload your raw data file (Excel)", type=["xlsx"])

    if uploaded_file is not None:
        # Load the uploaded file into a DataFrame
        df = load_input_data(uploaded_file)
        
        # Display a button to process the data
        if st.button("Process Data"):
            with st.spinner("Processing data..."):
                # Clean the data
                df = cleaning_data(df)

                # Load the model for mapping
                model = load_model()

                # Map code wilaya and commune
                wilaya_info = mapping_code_commune(commune_data, df, model)

                # Assign mapped values to the DataFrame
                df = assign_map_values(df, wilaya_info)

                # Store the processed DataFrame in session state
                st.session_state.df_processed = df

                st.success("Data processing completed!")

        # Display the cleaned data if it exists in session state
        if st.session_state.df_processed is not None:
            st.write("Cleaned Data:")
            st.dataframe(st.session_state.df_processed)

            # Save the cleaned DataFrame to a new file
            cleaned_file_name = "cleaned_" + uploaded_file.name
            with pd.ExcelWriter(cleaned_file_name, engine='xlsxwriter') as writer:
                st.session_state.df_processed.to_excel(writer, index=False, sheet_name='Cleaned Data')

            # Provide a download link for the cleaned file
            with open(cleaned_file_name, "rb") as file:
                st.download_button(
                    label="Download Cleaned Data as Excel",
                    data=file,
                    file_name=cleaned_file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

if __name__ == "__main__":
    main()