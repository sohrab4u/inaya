import streamlit as st
from streamlit_option_menu import option_menu
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import pandas as pd
import pdfkit
import io
import sqlite3
import bcrypt
import re
import os
import shutil

# Set page configuration as the first Streamlit command
st.set_page_config(page_title="Inaya Cloth - Ladies Specialist", layout="wide")

# Database Setup
Base = declarative_base()
engine = create_engine("sqlite:///inaya_cloth.db", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# Configure pdfkit to use wkhtmltopdf
def configure_pdfkit():
    wkhtmltopdf_path = shutil.which("wkhtmltopdf")  # Finds wkhtmltopdf in PATH
    error_message = None
    pdfkit_config = None

    if not wkhtmltopdf_path:
        # Try Windows-specific path
        wkhtmltopdf_path = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
        if os.path.exists(wkhtmltopdf_path):
            pdfkit_config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
        else:
            # Try Linux/Streamlit Cloud fallback path
            wkhtmltopdf_path = "/usr/bin/wkhtmltopdf"
            if os.path.exists(wkhtmltopdf_path):
                pdfkit_config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
            else:
                error_message = (
                    "wkhtmltopdf not found. PDF generation will be disabled. "
                    "Please install wkhtmltopdf locally (see https://github.com/JazzCore/python-pdfkit/wiki/Installing-wkhtmltopdf). "
                    "For Streamlit Cloud, add 'wkhtmltopdf' to packages.txt."
                )
    else:
        pdfkit_config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

    return pdfkit_config, error_message

# Database Models
class Stock(Base):
    __tablename__ = "stock"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    selling_price = Column(Float, nullable=False)
    mrp = Column(Float, nullable=False)

class GRN(Base):
    __tablename__ = "grn"
    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stock.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)

class Sale(Base):
    __tablename__ = "sale"
    id = Column(Integer, primary_key=True)
    customer_name = Column(String(100))
    customer_mobile = Column(String(15))
    customer_address = Column(String(255))
    date = Column(DateTime, default=datetime.utcnow)
    items = relationship("SaleItem", back_populates="sale")

class SaleItem(Base):
    __tablename__ = "sale_item"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sale.id"), nullable=False)
    stock_id = Column(Integer, ForeignKey("stock.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    sale = relationship("Sale", back_populates="items")
    stock = relationship("Stock")

class Return(Base):
    __tablename__ = "return"
    id = Column(Integer, primary_key=True)
    sale_item_id = Column(Integer, ForeignKey("sale_item.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    reason = Column(String(255))
    date = Column(DateTime, default=datetime.utcnow)
    sale_item = relationship("SaleItem")

class Delivery(Base):
    __tablename__ = "delivery"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sale.id"), nullable=False)
    status = Column(String(50), nullable=False)
    customer_name = Column(String(100))
    customer_mobile = Column(String(15))
    customer_address = Column(String(255))
    reason = Column(String(255))
    date = Column(DateTime, default=datetime.utcnow)
    items = relationship("DeliveryItem", back_populates="delivery")

class DeliveryItem(Base):
    __tablename__ = "delivery_item"
    id = Column(Integer, primary_key=True)
    delivery_id = Column(Integer, ForeignKey("delivery.id"), nullable=False)
    sale_item_id = Column(Integer, ForeignKey("sale_item.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    delivery = relationship("Delivery", back_populates="items")
    sale_item = relationship("SaleItem")

# Database Migration
def migrate_database():
    Base.metadata.create_all(engine)  # Create all tables before migrations
    conn = sqlite3.connect("inaya_cloth.db")
    cursor = conn.cursor()
    migration_messages = []
    
    # Check and migrate stock table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock';")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(stock);")
        columns = [col[1] for col in cursor.fetchall()]
        if "price" in columns and "selling_price" not in columns:
            cursor.execute("ALTER TABLE stock RENAME COLUMN price TO selling_price;")
            migration_messages.append("Renamed 'price' to 'selling_price' in stock table.")
        if "mrp" not in columns:
            cursor.execute("ALTER TABLE stock ADD COLUMN mrp FLOAT NOT NULL DEFAULT 0.0;")
            cursor.execute("UPDATE stock SET mrp = selling_price WHERE mrp = 0.0;")
            migration_messages.append("Added 'mrp' column to stock table.")
    
    # Check and migrate sale table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sale';")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(sale);")
        columns = [col[1] for col in cursor.fetchall()]
        if "stock_id" in columns:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sale_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER,
                    stock_id INTEGER,
                    quantity INTEGER,
                    total_price FLOAT,
                    FOREIGN KEY (sale_id) REFERENCES sale(id),
                    FOREIGN KEY (stock_id) REFERENCES stock(id)
                );
            """)
            cursor.execute("SELECT id, stock_id, quantity, total_price FROM sale WHERE stock_id IS NOT NULL;")
            for row in cursor.fetchall():
                sale_id, stock_id, quantity, total_price = row
                cursor.execute("INSERT INTO sale_item (sale_id, stock_id, quantity, total_price) VALUES (?, ?, ?, ?);",
                              (sale_id, stock_id, quantity, total_price))
            cursor.execute("""
                CREATE TABLE new_sale (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT,
                    customer_mobile TEXT,
                    customer_address TEXT,
                    date DATETIME
                );
            """)
            cursor.execute("""
                INSERT INTO new_sale (id, customer_name, customer_mobile, customer_address, date)
                SELECT id, customer_name, customer_mobile, customer_address, date FROM sale;
            """)
            cursor.execute("DROP TABLE sale;")
            cursor.execute("ALTER TABLE new_sale RENAME TO sale;")
            migration_messages.append("Migrated sale table to support multiple items.")
    
    # Check and migrate return table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='return';")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(return);")
        columns = [col[1] for col in cursor.fetchall()]
        if "sale_id" in columns:
            cursor.execute("ALTER TABLE return RENAME TO old_return;")
            cursor.execute("""
                CREATE TABLE return (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_item_id INTEGER,
                    quantity INTEGER,
                    reason TEXT,
                    date DATETIME,
                    FOREIGN KEY (sale_item_id) REFERENCES sale_item(id)
                );
            """)
            cursor.execute("""
                INSERT INTO return (id, sale_item_id, quantity, reason, date)
                SELECT r.id, si.id as sale_item_id, r.quantity, r.reason, r.date
                FROM old_return r
                JOIN sale_item si ON si.sale_id = r.sale_id;
            """)
            cursor.execute("DROP TABLE old_return;")
            migration_messages.append("Updated return table to reference sale items.")
    
    # Create delivery_item table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id INTEGER,
            sale_item_id INTEGER,
            quantity INTEGER,
            FOREIGN KEY (delivery_id) REFERENCES delivery(id),
            FOREIGN KEY (sale_item_id) REFERENCES sale_item(id)
        );
    """)
    
    # Check and clean duplicate users
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user';")
    if cursor.fetchone():
        cursor.execute("""
            DELETE FROM user
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM user
                GROUP BY email
            );
        """)
        migration_messages.append("Removed duplicate emails from user table.")
    
    conn.commit()
    conn.close()

    # Create default admin user
    session = Session()
    try:
        existing_user = session.query(User).filter_by(email="alam@gmail.com").first()
        if not existing_user:
            hashed_password = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            admin_user = User(
                name="Admin User",
                email="alam@gmail.com",
                password=hashed_password,
                role="Admin",
                is_active=True
            )
            session.add(admin_user)
            session.commit()
            migration_messages.append("Created default Admin user (email: alam@gmail.com).")
    except Exception as e:
        session.rollback()
        migration_messages.append(f"Error creating default admin user: {str(e)}")
    finally:
        session.close()
    
    return migration_messages

# Perform migration
migration_messages = migrate_database()

# Configure pdfkit after database setup
pdfkit_config, wkhtmltopdf_error = configure_pdfkit()

# Initialize session state
if "user" not in st.session_state:
    st.session_state.user = None
if "sale_items" not in st.session_state:
    st.session_state.sale_items = []
if "return_items" not in st.session_state:
    st.session_state.return_items = []
if "pickup_items" not in st.session_state:
    st.session_state.pickup_items = []
if "grn_items" not in st.session_state:
    st.session_state.grn_items = []

# Email validation
def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

# Login page
def login_page():
    st.markdown("""
        <div style="background-color: #7E3F8F; color: white; padding: 20px; text-align: center;">
            <h1>Inaya Cloth - Ladies Specialist</h1>
            <p>Thawe Road, Near SBI Bank, Rasul Market – 841428</p>
            <p>Mobile: 9936551234</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.header("Login")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if not email or not password:
                st.error("Email and password are required.")
            elif not is_valid_email(email):
                st.error("Invalid email format.")
            else:
                user = session.query(User).filter_by(email=email, is_active=True).first()
                if user and bcrypt.checkpw(password.encode("utf-8"), user.password.encode("utf-8")):
                    st.session_state.user = {"id": user.id, "name": user.name, "email": user.email, "role": user.role}
                    st.session_state.grn_items = []  # Reset GRN items on login
                    st.success(f"Welcome, {user.name}!")
                    st.rerun()
                else:
                    st.error("Invalid email or password.")

# Logout function
def logout():
    st.session_state.user = None
    st.session_state.sale_items = []
    st.session_state.return_items = []
    st.session_state.pickup_items = []
    st.session_state.grn_items = []
    st.success("Logged out successfully!")
    st.rerun()

# Main application
def main_app():
    if wkhtmltopdf_error:
        st.warning(wkhtmltopdf_error)
    
    if migration_messages:
        with st.expander("Database Migration Log"):
            for msg in migration_messages:
                st.write(msg)

    st.markdown("""
        <div style="background-color: #7E3F8F; color: white; padding: 20px; text-align: center;">
            <h1>Inaya Cloth - Ladies Specialist</h1>
            <p>Thawe Road, Near SBI Bank, Rasul Market – 841428</p>
            <p>Mobile: 9936551234</p>
        </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.write(f"Logged in as: {st.session_state.user['name']} ({st.session_state.user['role']})")
        if st.button("Logout"):
            logout()
        
        menu_options = ["Inventory Management", "Sale Management", "Delivery Management"]
        if st.session_state.user["role"] == "Admin":
            menu_options.append("User Management")
        
        selected = option_menu(
            "Main Menu",
            menu_options,
            icons=["box", "cart", "truck", "people"],
            menu_icon="shop",
            default_index=0,
            styles={
                "container": {"background-color": "#f3e8ff"},
                "nav-link-selected": {"background-color": "#7E3F8F"},
            }
        )

    if selected == "Inventory Management":
        st.header("Inventory Management")
        tab1, tab2, tab3 = st.tabs(["Create Stock", "Create GRN", "Reports"])

        with tab1:
            st.subheader("Create Stock")
            with st.form("create_stock_form"):
                name = st.text_input("Item Name")
                quantity = st.number_input("Quantity", min_value=0, step=1)
                selling_price = st.number_input("Selling Price (Rs.)", min_value=0.0, step=0.01)
                mrp = st.number_input("MRP (Rs.)", min_value=0.0, step=0.01)
                if st.form_submit_button("Add Stock"):
                    if not name or not selling_price or not mrp:
                        st.error("All fields are required.")
                    elif mrp < selling_price:
                        st.error("MRP cannot be less than Selling Price.")
                    elif quantity < 0:
                        st.error("Quantity cannot be negative.")
                    else:
                        stock = Stock(name=name, quantity=quantity, selling_price=selling_price, mrp=mrp)
                        session.add(stock)
                        try:
                            session.commit()
                            st.success("Stock created successfully!")
                        except Exception as e:
                            session.rollback()
                            st.error(f"Error creating stock: {str(e)}")

        with tab2:
            st.subheader("Create GRN")
            stocks = session.query(Stock).all()
            stock_options = {f"{s.name} (ID: {s.id})": s.id for s in stocks}
            with st.form("add_grn_item_form"):
                col1, col2 = st.columns(2)
                with col1:
                    stock_id = st.selectbox("Select Item", options=list(stock_options.keys()))
                with col2:
                    quantity = st.number_input("Quantity", min_value=1, step=1)
                if st.form_submit_button("Add Item"):
                    if not stock_id or not quantity:
                        st.error("All fields are required.")
                    elif quantity < 1:
                        st.error("Quantity must be at least 1.")
                    else:
                        stock = session.query(Stock).get(stock_options[stock_id])
                        st.session_state.grn_items.append({"stock_id": stock_options[stock_id], "quantity": quantity})
                        st.success(f"Added {quantity} of {stock.name} to GRN.")
            
            if st.session_state.grn_items:
                st.write("Selected Items:")
                grn_items_df = pd.DataFrame([
                    {"Item": session.query(Stock).get(item["stock_id"]).name, "Quantity": item["quantity"]}
                    for item in st.session_state.grn_items
                ])
                st.dataframe(grn_items_df, use_container_width=True)
            
            with st.form("submit_grn_form"):
                if st.form_submit_button("Submit GRN"):
                    if not st.session_state.grn_items:
                        st.error("No items added to GRN.")
                    else:
                        try:
                            for item in st.session_state.grn_items:
                                stock = session.query(Stock).get(item["stock_id"])
                                if not stock:
                                    st.error(f"Stock item ID {item['stock_id']} not found.")
                                    session.rollback()
                                    break
                                grn = GRN(stock_id=stock.id, quantity=item["quantity"])
                                stock.quantity += item["quantity"]
                                session.add(grn)
                            else:
                                session.commit()
                                st.session_state.grn_items = []
                                st.success("GRN created successfully for all items!")
                                st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Error creating GRN: {str(e)}")

        with tab3:
            st.subheader("Stock Report")
            stocks = session.query(Stock).all()
            df = pd.DataFrame([(s.id, s.name, s.quantity, f"Rs. {s.selling_price:.2f}", f"Rs. {s.mrp:.2f}") for s in stocks], 
                             columns=["ID", "Name", "Quantity", "Selling Price", "MRP"])
            st.dataframe(df, use_container_width=True)

            st.subheader("Adjust Stock")
            with st.form("adjust_stock_form"):
                stock_id = st.selectbox("Select Item to Adjust", options=list(stock_options.keys()))
                new_quantity = st.number_input("New Quantity", min_value=0, step=1)
                if st.form_submit_button("Adjust"):
                    if new_quantity < 0:
                        st.error("New quantity cannot be negative.")
                    else:
                        stock = session.query(Stock).get(stock_options[stock_id])
                        stock.quantity = new_quantity
                        try:
                            session.commit()
                            st.success("Stock adjusted successfully!")
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Error adjusting stock: {str(e)}")

            st.subheader("GRN Report")
            grns = session.query(GRN).all()
            grn_data = []
            for grn in grns:
                stock = session.query(Stock).get(grn.stock_id)
                total_price = grn.quantity * stock.selling_price
                grn_data.append((grn.id, stock.name, grn.quantity, 
                                f"Rs. {stock.mrp:.2f}",
                                f"Rs. {stock.selling_price:.2f}",
                                f"Rs. {total_price:.2f}",
                                grn.date.strftime("%Y-%m-%d")))
            df_grn = pd.DataFrame(grn_data, 
                                 columns=["GRN ID", "Item Name", "Quantity", "MRP", "Selling Price", "Total Selling Price", "Date"])
            st.dataframe(df_grn, use_container_width=True)

            st.subheader("GRN Invoice")
            grn_options = {f"GRN {g.id} ({g.date.strftime('%Y-%m-%d')})": g.id for g in grns}
            selected_grn = st.selectbox("Select GRN for Invoice", options=list(grn_options.keys()))
            if st.button("Generate GRN Invoice"):
                try:
                    grn = session.query(GRN).get(grn_options[selected_grn])
                    stock = session.query(Stock).get(grn.stock_id)
                    total_price = grn.quantity * stock.selling_price
                    html = f"""
                        <div style="font-family: Arial, sans-serif; width: 800px; margin: 0 auto; padding: 20px; border: 2px solid #7E3F8F;">
                            <div style="text-align: center; margin-bottom: 20px;">
                                <h1 style="color: #7E3F8F;">Inaya Cloth</h1>
                                <p style="font-size: 0.9em;">Ladies Specialist</p>
                                <p style="font-size: 0.9em;">Thawe Road, Near SBI Bank, Rasul Market – 841428</p>
                                <p style="font-size: 0.9em;">Mobile: 9936551234</p>
                            </div>
                            <hr style="border: 1px solid #7E3F8F;">
                            <h2 style="text-align: center;">Goods Received Note (GRN)</h2>
                            <table style="width: 100%; font-size: 0.9em;">
                                <tr>
                                    <td><strong>GRN ID:</strong> {grn.id}</td>
                                    <td style="text-align: right;"><strong>Date:</strong> {grn.date.strftime('%Y-%m-%d')}</td>
                                </tr>
                            </table>
                            <table border="1" style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                <tr style="background-color: #f3e8ff;">
                                    <th style="padding: 10px;">Item Name</th>
                                    <th style="padding: 10px;">Quantity</th>
                                    <th style="padding: 10px;">MRP</th>
                                    <th style="padding: 10px;">Selling Price</th>
                                    <th style="padding: 10px;">Total Selling Price</th>
                                </tr>
                                <tr>
                                    <td style="padding: 10px;">{stock.name}</td>
                                    <td style="padding: 10px;">{grn.quantity}</td>
                                    <td style="padding: 10px;">Rs. {stock.mrp:.2f}</td>
                                    <td style="padding: 10px;">Rs. {stock.selling_price:.2f}</td>
                                    <td style="padding: 10px;">Rs. {total_price:.2f}</td>
                                </tr>
                            </table>
                            <div style="text-align: center; margin-top: 20px;">
                                <p style="font-size: 0.8em;">Thank you for choosing Inaya Cloth!</p>
                            </div>
                        </div>
                    """
                    if pdfkit_config:
                        pdf_bytes = pdfkit.from_string(html, False, configuration=pdfkit_config)
                        pdf_io = io.BytesIO(pdf_bytes)
                        st.download_button(
                            label="Download GRN Invoice",
                            data=pdf_io,
                            file_name=f"grn_{grn.id}.pdf",
                            mime="application/pdf"
                        )
                    else:
                        st.error("Cannot generate PDF due to missing wkhtmltopdf configuration.")
                except Exception as e:
                    st.error(f"Error generating PDF: {str(e)}")

    elif selected == "User Management":
        if st.session_state.user["role"] != "Admin":
            st.error("Access denied: Only Admins can access User Management.")
        else:
            st.header("User Management")
            tab1, tab2 = st.tabs(["Create User", "Reports"])

            with tab1:
                st.subheader("Create User")
                with st.form("create_user_form"):
                    name = st.text_input("Name")
                    email = st.text_input("Email")
                    password = st.text_input("Password", type="password")
                    role = st.selectbox("Role", ["Salesman", "Admin", "Delivery Boy"])
                    if st.form_submit_button("Add User"):
                        if not name or not email or not password:
                            st.error("All fields are required.")
                        elif not is_valid_email(email):
                            st.error("Invalid email format.")
                        else:
                            existing_user = session.query(User).filter_by(email=email).first()
                            if existing_user:
                                st.error(f"User with email {email} already exists.")
                            else:
                                hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                                user = User(name=name, email=email, password=hashed_password, role=role)
                                session.add(user)
                                try:
                                    session.commit()
                                    st.success("User created successfully!")
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"Error creating user: {str(e)}")

            with tab2:
                st.subheader("User Report")
                users = session.query(User).all()
                df = pd.DataFrame([(u.id, u.name, u.email, u.role, "Active" if u.is_active else "Inactive") 
                                  for u in users], 
                                 columns=["ID", "Name", "Email", "Role", "Status"])
                st.dataframe(df, use_container_width=True)

                st.subheader("Manage Users")
                user_options = {f"{u.name} (ID: {u.id})": u.id for u in users}
                selected_user = st.selectbox("Select User", options=list(user_options.keys()))
                user = session.query(User).get(user_options[selected_user])
                if user.is_active:
                    if st.button("Delete User"):
                        user.is_active = False
                        try:
                            session.commit()
                            st.success("User deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Error deleting user: {str(e)}")
                else:
                    if st.button("Activate User"):
                        user.is_active = True
                        try:
                            session.commit()
                            st.success("User activated successfully!")
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Error activating user: {str(e)}")

    elif selected == "Sale Management":
        st.header("Sale Management")
        tab1, tab2 = st.tabs(["Sell Item", "Return Item"])

        with tab1:
            st.subheader("Sell Item")
            stocks = session.query(Stock).all()
            stock_options = {f"{s.name} (ID: {s.id})": s.id for s in stocks}
            
            with st.form("sell_form"):
                col1, col2 = st.columns(2)
                with col1:
                    stock_id = st.selectbox("Select Item", options=list(stock_options.keys()))
                with col2:
                    quantity = st.number_input("Quantity", min_value=1, step=1)
                
                if st.form_submit_button("Add Item"):
                    if not stock_id or not quantity:
                        st.error("All fields are required.")
                    elif quantity < 1:
                        st.error("Quantity must be at least 1.")
                    else:
                        stock = session.query(Stock).get(stock_options[stock_id])
                        if stock.quantity >= quantity:
                            st.session_state.sale_items.append({"stock_id": stock_options[stock_id], "quantity": quantity})
                            st.success(f"Added {quantity} of {stock.name} to sale.")
                        else:
                            st.error(f"Insufficient stock: only {stock.quantity} available for {stock.name}.")
                
                st.write("Selected Items:")
                for item in st.session_state.sale_items:
                    stock = session.query(Stock).get(item["stock_id"])
                    st.write(f"Item: {stock.name}, Quantity: {item['quantity']}")
                
                customer_name = st.text_input("Customer Name")
                customer_mobile = st.text_input("Customer Mobile")
                customer_address = st.text_input("Customer Address")
                
                if st.form_submit_button("Complete Sale"):
                    if not st.session_state.sale_items:
                        st.error("No items added to sale.")
                    elif not customer_name or not customer_mobile or not customer_address:
                        st.error("Customer details are required.")
                    else:
                        sale = Sale(customer_name=customer_name, customer_mobile=customer_mobile, customer_address=customer_address)
                        session.add(sale)
                        session.flush()
                        for item in st.session_state.sale_items:
                            stock = session.query(Stock).get(item["stock_id"])
                            if stock.quantity < item["quantity"]:
                                st.error(f"Insufficient stock for {stock.name}: only {stock.quantity} available.")
                                session.rollback()
                                break
                            sale_item = SaleItem(
                                sale_id=sale.id,
                                stock_id=item["stock_id"],
                                quantity=item["quantity"],
                                total_price=item["quantity"] * stock.selling_price
                            )
                            stock.quantity -= item["quantity"]
                            session.add(sale_item)
                        else:
                            try:
                                session.commit()
                                st.session_state.sale_items = []
                                st.success("Sale completed successfully!")
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Error completing sale: {str(e)}")
        
            sales = session.query(Sale).all()
            if sales:
                latest_sale = session.query(Sale).order_by(Sale.id.desc()).first()
                sale_items = session.query(SaleItem).filter_by(sale_id=latest_sale.id).all()
                if st.button("Generate Sale Invoice"):
                    try:
                        items_html = ""
                        grand_total = 0
                        for item in sale_items:
                            stock = session.query(Stock).get(item.stock_id)
                            total = item.total_price
                            grand_total += total
                            items_html += f"""
                                <tr>
                                    <td style="padding: 10px;">{stock.name}</td>
                                    <td style="padding: 10px;">{item.quantity}</td>
                                    <td style="padding: 10px;">Rs. {stock.mrp:.2f}</td>
                                    <td style="padding: 10px;">Rs. {stock.selling_price:.2f}</td>
                                    <td style="padding: 10px;">Rs. {total:.2f}</td>
                                </tr>
                            """
                        customer_name = latest_sale.customer_name or "N/A"
                        customer_mobile = latest_sale.customer_mobile or "N/A"
                        customer_address = latest_sale.customer_address or "N/A"
                        html = f"""
                            <div style="font-family: Arial, sans-serif; width: 800px; margin: 0 auto; padding: 20px; border: 2px solid #7E3F8F;">
                                <div style="text-align: center; margin-bottom: 20px;">
                                    <h1 style="color: #7E3F8F;">Inaya Cloth</h1>
                                <p style="font-size: 0.9em;">Ladies Specialist</p>
                                    <p style="font-size: 0.9em;">Thawe Road, Near SBI Bank, Rasul Market – 841428</p>
                                    <p style="font-size: 0.9em;">Mobile: 9936551234</p>
                                </div>
                                <hr style="border: 1px solid #7E3F8F;">
                                <h2 style="text-align: center;">Sale Invoice</h2>
                                <table style="width: 100%; font-size: 0.9em;">
                                    <tr>
                                        <td><strong>Sale ID:</strong> {latest_sale.id}</td>
                                        <td style="text-align: right;"><strong>Date:</strong> {latest_sale.date.strftime('%Y-%m-%d')}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Customer:</strong> {customer_name}</td>
                                        <td style="text-align: right;"><strong>Mobile:</strong> {customer_mobile}</td>
                                    </tr>
                                    <tr>
                                        <td colspan="2"><strong>Address:</strong> {customer_address}</td>
                                    </tr>
                                </table>
                                <table border="1" style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                    <tr style="background-color: #f3e8ff;">
                                        <th style="padding: 10px;">Item Name</th>
                                        <th style="padding: 10px;">Quantity</th>
                                        <th style="padding: 10px;">MRP</th>
                                        <th style="padding: 10px;">Selling Price</th>
                                        <th style="padding: 10px;">Total</th>
                                    </tr>
                                    {items_html}
                                    <tr style="background-color: #f3e8ff;">
                                        <td colspan="4" style="padding: 10px; text-align: right;"><strong>Grand Total:</strong></td>
                                        <td style="padding: 10px;">Rs. {grand_total:.2f}</td>
                                    </tr>
                                </table>
                                <div style="text-align: center; margin-top: 20px;">
                                    <p style="font-size: 0.8em;">Thank you for choosing Inaya Cloth!</p>
                                </div>
                            </div>
                        """
                        if pdfkit_config:
                            pdf_bytes = pdfkit.from_string(html, False, configuration=pdfkit_config)
                            pdf_io = io.BytesIO(pdf_bytes)
                            st.download_button(
                                label="Download Sale Invoice",
                                data=pdf_io,
                                file_name=f"sale_{latest_sale.id}.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.error("Cannot generate PDF due to missing wkhtmltopdf configuration.")
                    except Exception as e:
                        st.error(f"Error generating PDF: {str(e)}")

        with tab2:
            st.subheader("Return Item")
            sales = session.query(Sale).all()
            sale_options = {f"Sale {s.id} ({s.customer_name or 'No Name'})": s.id for s in sales}
            
            sale_id = st.selectbox("Select Sale", options=list(sale_options.keys()))
            if sale_id:
                sale_items = session.query(SaleItem).filter_by(sale_id=sale_options[sale_id]).all()
                valid_sale_items = [si for si in sale_items if si.quantity > 0]
                
                if not valid_sale_items:
                    st.warning("No items available to return for this sale.")
                else:
                    st.write("Items in Sale:")
                    for item in valid_sale_items:
                        stock = session.query(Stock).get(item.stock_id)
                        st.write(f"Item: {stock.name}, Quantity Available: {item.quantity}, Total: Rs. {item.total_price:.2f}")
                    
                    with st.form("add_return_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            sale_item_options = [f"{session.query(Stock).get(si.stock_id).name} (ID: {si.id})" for si in valid_sale_items]
                            sale_item_id = st.selectbox("Select Item to Return", options=sale_item_options)
                        with col2:
                            selected_sale_item = next(si for si in valid_sale_items if f"{session.query(Stock).get(si.stock_id).name} (ID: {si.id})" == sale_item_id)
                            max_quantity = selected_sale_item.quantity
                            quantity = st.number_input("Quantity to Return", min_value=1, max_value=max_quantity, step=1)
                        
                        reason = st.text_input("Reason for Return")
                        
                        if st.form_submit_button("Add to Return"):
                            if not sale_item_id or not quantity or not reason:
                                st.error("All fields are required.")
                            elif quantity > selected_sale_item.quantity:
                                st.error(f"Cannot return {quantity} units. Only {selected_sale_item.quantity} available.")
                            else:
                                st.session_state.return_items.append({
                                    "sale_item_id": selected_sale_item.id,
                                    "quantity": quantity,
                                    "reason": reason
                                })
                                st.success(f"Added {quantity} units to return.")
                    
                    st.write("Items to Return:")
                    for item in st.session_state.return_items:
                        sale_item = session.query(SaleItem).get(item["sale_item_id"])
                        stock = session.query(Stock).get(sale_item.stock_id)
                        st.write(f"Item: {stock.name}, Quantity: {item['quantity']}, Reason: {item['reason']}")
                    
                    with st.form("complete_return_form"):
                        if st.form_submit_button("Complete Return"):
                            if not st.session_state.return_items:
                                st.error("No items added to return.")
                            else:
                                for item in st.session_state.return_items:
                                    sale_item = session.query(SaleItem).get(item["sale_item_id"])
                                    if item["quantity"] > sale_item.quantity:
                                        st.error(f"Cannot return {item['quantity']} units of item ID {sale_item.id}. Only {sale_item.quantity} available.")
                                        session.rollback()
                                        break
                                    if sale_item.quantity - item["quantity"] < 0:
                                        st.error(f"Return would result in negative quantity for item ID {sale_item.id}.")
                                        session.rollback()
                                        break
                                    return_entry = Return(
                                        sale_item_id=item["sale_item_id"],
                                        quantity=item["quantity"],
                                        reason=item["reason"]
                                    )
                                    stock = session.query(Stock).get(sale_item.stock_id)
                                    stock.quantity += item["quantity"]
                                    sale_item.quantity -= item["quantity"]
                                    sale_item.total_price = sale_item.quantity * stock.selling_price
                                    session.add(return_entry)
                                else:
                                    try:
                                        session.commit()
                                        st.session_state.return_items = []
                                        st.success("Return processed successfully!")
                                        st.rerun()
                                    except Exception as e:
                                        session.rollback()
                                        st.error(f"Error processing return: {str(e)}")
            
            returns = session.query(Return).all()
            if returns:
                latest_return = session.query(Return).order_by(Return.id.desc()).first()
                sale_item = session.query(SaleItem).get(latest_return.sale_item_id)
                stock = session.query(Stock).get(sale_item.stock_id)
                total_amount = latest_return.quantity * stock.selling_price
                if st.button("Generate Return Invoice"):
                    try:
                        html = f"""
                            <div style="font-family: Arial, sans-serif; width: 800px; margin: 0 auto; padding: 20px; border: 2px solid #7E3F8F;">
                                <div style="text-align: center; margin-bottom: 20px;">
                                    <h1 style="color: #7E3F8F;">Inaya Cloth</h1>
                                    <p style="font-size: 0.9em;">Ladies Specialist</p>
                                    <p style="font-size: 0.9em;">Thawe Road, Near SBI Bank, Rasul Market – 841428</p>
                                    <p style="font-size: 0.9em;">Mobile: 9936551234</p>
                                </div>
                                <hr style="border: 1px solid #7E3F8F;">
                                <h2 style="text-align: center;">Return Invoice</h2>
                                <table style="width: 100%; font-size: 0.9em;">
                                    <tr>
                                        <td><strong>Return ID:</strong> {latest_return.id}</td>
                                        <td style="text-align: right;"><strong>Date:</strong> {latest_return.date.strftime('%Y-%m-%d')}</td>
                                    </tr>
                                    <tr>
                                        <td colspan="2"><strong>Reason:</strong> {latest_return.reason}</td>
                                    </tr>
                                </table>
                                <table border="1" style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                    <tr style="background-color: #f3e8ff;">
                                        <th style="padding: 10px;">Item Name</th>
                                        <th style="padding: 10px;">Quantity</th>
                                        <th style="padding: 10px;">Selling Price</th>
                                        <th style="padding: 10px;">Total Amount</th>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px;">{stock.name}</td>
                                        <td style="padding: 10px;">{latest_return.quantity}</td>
                                        <td style="padding: 10px;">Rs. {stock.selling_price:.2f}</td>
                                        <td style="padding: 10px;">Rs. {total_amount:.2f}</td>
                                    </tr>
                                </table>
                                <div style="text-align: center; margin-top: 20px;">
                                    <p style="font-size: 0.8em;">Thank you for choosing Inaya Cloth!</p>
                                </div>
                            </div>
                        """
                        if pdfkit_config:
                            pdf_bytes = pdfkit.from_string(html, False, configuration=pdfkit_config)
                            pdf_io = io.BytesIO(pdf_bytes)
                            st.download_button(
                                label="Download Return Invoice",
                                data=pdf_io,
                                file_name=f"return_{latest_return.id}.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.error("Cannot generate PDF due to missing wkhtmltopdf configuration.")
                    except Exception as e:
                        st.error(f"Error generating PDF: {str(e)}")

    elif selected == "Delivery Management":
        st.header("Delivery Management")
        tab1, tab2 = st.tabs(["Pickup Item", "Delivery Report"])

        with tab1:
            st.subheader("Pickup Item")
            stocks = session.query(Stock).all()
            stock_options = {f"{s.name} (ID: {s.id})": s.id for s in stocks}
            
            with st.form("add_delivery_item_form"):
                col1, col2 = st.columns(2)
                with col1:
                    stock_id = st.selectbox("Select Item", options=list(stock_options.keys()))
                with col2:
                    quantity = st.number_input("Quantity", min_value=1, step=1)
                
                if st.form_submit_button("Add Item"):
                    if not stock_id or not quantity:
                        st.error("All fields are required.")
                    elif quantity < 1:
                        st.error("Quantity must be at least 1.")
                    else:
                        stock = session.query(Stock).get(stock_options[stock_id])
                        if stock.quantity >= quantity:
                            st.session_state.pickup_items.append({
                                "stock_id": stock_options[stock_id],
                                "quantity": quantity
                            })
                            st.success(f"Added {quantity} of {stock.name} for delivery.")
                        else:
                            st.error(f"Insufficient stock: only {stock.quantity} available for {stock.name}.")
            
            if st.session_state.pickup_items:
                st.write("Items to Pickup:")
                pickup_items_df = pd.DataFrame([
                    {
                        "Item": session.query(Stock).get(item["stock_id"]).name,
                        "Quantity": item["quantity"]
                    }
                    for item in st.session_state.pickup_items
                ])
                st.dataframe(pickup_items_df, use_container_width=True)
            
            with st.form("complete_pickup_form"):
                customer_name = st.text_input("Customer Name")
                customer_mobile = st.text_input("Customer Mobile")
                customer_address = st.text_area("Delivery Address")
                
                if st.form_submit_button("Complete Pickup"):
                    if not st.session_state.pickup_items:
                        st.error("No items added to pickup.")
                    elif not customer_name or not customer_mobile or not customer_address:
                        st.error("Customer details are required.")
                    else:
                        try:
                            # Create Sale
                            sale = Sale(
                                customer_name=customer_name,
                                customer_mobile=customer_mobile,
                                customer_address=customer_address
                            )
                            session.add(sale)
                            session.flush()
                            # Create Delivery
                            delivery = Delivery(
                                sale_id=sale.id,
                                status="Picked",
                                customer_name=customer_name,
                                customer_mobile=customer_mobile,
                                customer_address=customer_address
                            )
                            session.add(delivery)
                            session.flush()
                            # Process items
                            for item in st.session_state.pickup_items:
                                stock = session.query(Stock).get(item["stock_id"])
                                if stock.quantity < item["quantity"]:
                                    st.error(f"Insufficient stock for {stock.name}: only {stock.quantity} available.")
                                    session.rollback()
                                    break
                                # Create SaleItem
                                sale_item = SaleItem(
                                    sale_id=sale.id,
                                    stock_id=item["stock_id"],
                                    quantity=item["quantity"],
                                    total_price=item["quantity"] * stock.selling_price
                                )
                                stock.quantity -= item["quantity"]
                                session.add(sale_item)
                                session.flush()
                                # Create DeliveryItem
                                delivery_item = DeliveryItem(
                                    delivery_id=delivery.id,
                                    sale_item_id=sale_item.id,
                                    quantity=item["quantity"]
                                )
                                session.add(delivery_item)
                            else:
                                session.commit()
                                st.session_state.pickup_items = []
                                st.success("Delivery pickup completed successfully!")
                                st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"Error completing pickup: {str(e)}")

        with tab2:
            st.subheader("Delivery Report")
            deliveries = session.query(Delivery).all()
            delivery_data = [(d.id, d.sale_id, d.status, d.customer_name or "N/A", d.customer_mobile or "N/A", 
                             d.customer_address or "N/A", d.reason or "N/A") for d in deliveries]
            df_delivery = pd.DataFrame(delivery_data, 
                                      columns=["ID", "Sale ID", "Status", "Customer Name", "Mobile", "Address", "Reason"])
            st.dataframe(df_delivery, use_container_width=True)

            if deliveries:
                delivery_options = {f"Delivery {d.id} (Sale ID {d.sale_id})": d.id for d in deliveries}
                selected_delivery = st.selectbox("Select Delivery", options=list(delivery_options.keys()))
                delivery = session.query(Delivery).get(delivery_options[selected_delivery])
                
                col1, col2 = st.columns(2)
                with col1:
                    if delivery.status != "Delivered":
                        if st.button("Mark as Delivered"):
                            delivery.status = "Delivered"
                            try:
                                session.commit()
                                st.session_state.recent_delivered = delivery.id
                                st.success("Delivery marked as completed!")
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Error marking delivery: {str(e)}")
                    if delivery.status == "Delivered" and st.session_state.get("recent_delivered") == delivery.id:
                        if st.button("Generate Sale Invoice"):
                            try:
                                sale = session.query(Sale).get(delivery.sale_id)
                                sale_items = session.query(SaleItem).filter_by(sale_id=sale.id).all()
                                items_html = ""
                                grand_total = 0
                                for item in sale_items:
                                    stock = session.query(Stock).get(item.stock_id)
                                    total = item.total_price
                                    grand_total += total
                                    items_html += f"""
                                        <tr>
                                            <td style="padding: 10px;">{stock.name}</td>
                                            <td style="padding: 10px;">{item.quantity}</td>
                                            <td style="padding: 10px;">Rs. {stock.mrp:.2f}</td>
                                            <td style="padding: 10px;">Rs. {stock.selling_price:.2f}</td>
                                            <td style="padding: 10px;">Rs. {total:.2f}</td>
                                        </tr>
                                    """
                                customer_name = sale.customer_name or "N/A"
                                customer_mobile = sale.customer_mobile or "N/A"
                                customer_address = sale.customer_address or "N/A"
                                html = f"""
                                    <div style="font-family: Arial, sans-serif; width: 800px; margin: 0 auto; padding: 20px; border: 2px solid #7E3F8F;">
                                        <div style="text-align: center; margin-bottom: 20px;">
                                            <h1 style="color: #7E3F8F;">Inaya Cloth</h1>
                                            <p style="font-size: 0.9em;">Ladies Specialist</p>
                                            <p style="font-size: 0.9em;">Thawe Road, Near SBI Bank, Rasul Market – 841428</p>
                                            <p style="font-size: 0.9em;">Mobile: 9936551234</p>
                                        </div>
                                        <hr style="border: 1px solid #7E3F8F;">
                                        <h2 style="text-align: center;">Sale Invoice</h2>
                                        <table style="width: 100%; font-size: 0.9em;">
                                            <tr>
                                                <td><strong>Sale ID:</strong> {sale.id}</td>
                                                <td style="text-align: right;"><strong>Date:</strong> {sale.date.strftime('%Y-%m-%d')}</td>
                                            </tr>
                                            <tr>
                                                <td><strong>Customer:</strong> {customer_name}</td>
                                                <td style="text-align: right;"><strong>Mobile:</strong> {customer_mobile}</td>
                                            </tr>
                                            <tr>
                                                <td colspan="2"><strong>Address:</strong> {customer_address}</td>
                                            </tr>
                                        </table>
                                        <table border="1" style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                            <tr style="background-color: #f3e8ff;">
                                                <th style="padding: 10px;">Item Name</th>
                                                <th style="padding: 10px;">Quantity</th>
                                                <th style="padding: 10px;">MRP</th>
                                                <th style="padding: 10px;">Selling Price</th>
                                                <th style="padding: 10px;">Total</th>
                                            </tr>
                                            {items_html}
                                            <tr style="background-color: #f3e8ff;">
                                                <td colspan="4" style="padding: 10px; text-align: right;"><strong>Grand Total:</strong></td>
                                                <td style="padding: 10px;">Rs. {grand_total:.2f}</td>
                                            </tr>
                                        </table>
                                        <div style="text-align: center; margin-top: 20px;">
                                            <p style="font-size: 0.8em;">Thank you for choosing Inaya Cloth!</p>
                                        </div>
                                    </div>
                                """
                                if pdfkit_config:
                                    pdf_bytes = pdfkit.from_string(html, False, configuration=pdfkit_config)
                                    pdf_io = io.BytesIO(pdf_bytes)
                                    st.download_button(
                                        label="Download Sale Invoice",
                                        data=pdf_io,
                                        file_name=f"sale_{sale.id}.pdf",
                                        mime="application/pdf"
                                    )
                                else:
                                    st.error("Cannot generate PDF due to missing wkhtmltopdf configuration.")
                            except Exception as e:
                                st.error(f"Error generating PDF: {str(e)}")
                with col2:
                    with st.form("return_delivery_form"):
                        reason = st.text_input("Reason for Return")
                        if st.form_submit_button("Submit"):
                            if not reason:
                                st.error("Reason for return is required.")
                            else:
                                delivery.status = "Cancelled"
                                delivery.reason = reason
                                # Update stock quantities
                                delivery_items = session.query(DeliveryItem).filter_by(delivery_id=delivery.id).all()
                                for item in delivery_items:
                                    sale_item = session.query(SaleItem).get(item.sale_item_id)
                                    stock = session.query(Stock).get(sale_item.stock_id)
                                    stock.quantity += item.quantity
                                if "recent_delivered" in st.session_state:
                                    del st.session_state.recent_delivered
                                try:
                                    session.commit()
                                    st.success("Delivery cancelled successfully and stock updated!")
                                    st.rerun()
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"Error returning delivery: {str(e)}")
            else:
                st.warning("No deliveries available.")
            
            if st.button("Generate Delivery Invoice"):
                try:
                    delivery_items = session.query(DeliveryItem).filter_by(delivery_id=delivery.id).all()
                    items_html = ""
                    grand_total = 0
                    for item in delivery_items:
                        sale_item = session.query(SaleItem).get(item.sale_item_id)
                        stock = session.query(Stock).get(sale_item.stock_id)
                        total = item.quantity * stock.selling_price
                        grand_total += total
                        items_html += f"""
                            <tr>
                                <td style="padding: 10px;">{stock.name}</td>
                                <td style="padding: 10px;">{item.quantity}</td>
                                <td style="padding: 10px;">Rs. {stock.mrp:.2f}</td>
                                <td style="padding: 10px;">Rs. {stock.selling_price:.2f}</td>
                                <td style="padding: 10px;">Rs. {total:.2f}</td>
                            </tr>
                        """
                    customer_name = delivery.customer_name or "N/A"
                    customer_mobile = delivery.customer_mobile or "N/A"
                    customer_address = delivery.customer_address or "N/A"
                    html = f"""
                        <div style="font-family: Arial, sans-serif; width: 800px; margin: 0 auto; padding: 20px; border: 2px solid #7E3F8F;">
                            <div style="text-align: center; margin-bottom: 20px;">
                                <h1 style="color: #7E3F8F;">Inaya Cloth</h1>
                                <p style="font-size: 0.9em;">Ladies Specialist</p>
                                <p style="font-size: 0.9em;">Thawe Road, Near SBI Bank, Rasul Market – 841428</p>
                                <p style="font-size: 0.9em;">Mobile: 9936551234</p>
                            </div>
                            <hr style="border: 1px solid #7E3F8F;">
                            <h2 style="text-align: center;">Delivery Invoice</h2>
                            <table style="width: 100%; font-size: 0.9em;">
                                <tr>
                                    <td><strong>Delivery ID:</strong> {delivery.id}</td>
                                    <td style="text-align: right;"><strong>Date:</strong> {delivery.date.strftime('%Y-%m-%d')}</td>
                                </tr>
                                <tr>
                                    <td><strong>Customer:</strong> {customer_name}</td>
                                    <td style="text-align: right;"><strong>Mobile:</strong> {customer_mobile}</td>
                                </tr>
                                <tr>
                                    <td colspan="2"><strong>Address:</strong> {customer_address}</td>
                                </tr>
                                <tr>
                                    <td><strong>Status:</strong> {delivery.status}</td>
                                    <td style="text-align: right;"><strong>Sale ID:</strong> {delivery.sale_id}</td>
                                </tr>
                            </table>
                            <table border="1" style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                                <tr style="background-color: #f3e8ff;">
                                    <th style="padding: 10px;">Item Name</th>
                                    <th style="padding: 10px;">Quantity</th>
                                    <th style="padding: 10px;">MRP</th>
                                    <th style="padding: 10px;">Selling Price</th>
                                    <th style="padding: 10px;">Total</th>
                                </tr>
                                {items_html}
                                <tr style="background-color: #f3e8ff;">
                                    <td colspan="4" style="padding: 10px; text-align: right;"><strong>Grand Total:</strong></td>
                                    <td style="padding: 10px;">Rs. {grand_total:.2f}</td>
                                </tr>
                            </table>
                            <div style="text-align: center; margin-top: 20px;">
                                <p style="font-size: 0.8em;">Thank you for choosing Inaya Cloth!</p>
                            </div>
                        </div>
                    """
                    if pdfkit_config:
                        pdf_bytes = pdfkit.from_string(html, False, configuration=pdfkit_config)
                        pdf_io = io.BytesIO(pdf_bytes)
                        st.download_button(
                            label="Download Delivery Invoice",
                            data=pdf_io,
                            file_name=f"delivery_{delivery.id}.pdf",
                            mime="application/pdf"
                        )
                    else:
                        st.error("Cannot generate PDF due to missing wkhtmltopdf configuration.")
                except Exception as e:
                    st.error(f"Error generating PDF: {str(e)}")

# Run the app
if st.session_state.user is None:
    login_page()
else:
    main_app()