# =============================================================================
# Myki Inspector Priority Dashboard - Flask Application
# =============================================================================
# This application provides a real-time dashboard for monitoring fare compliance
# across Melbourne's public transport network (Myki system).
# 
# Features:
# - Real-time evasion monitoring and alerts
# - Interactive station map with risk visualization
# - Comprehensive analytics and reporting
# - Secure login system
# - RESTful API endpoints
# =============================================================================

# Import required libraries
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd  # For data manipulation and analysis
import os  # For file system operations
import random  # For generating realistic data variations
import json  # For user management
from datetime import datetime, timedelta  # For timestamp handling
from dotenv import load_dotenv  # For environment variable management

# Load environment variables from .env file for secure configuration
load_dotenv()

# Initialize Flask application
app = Flask(__name__)
# Set secret key for session management (from environment or fallback)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'myki-inspector-portal-secret-key-2024')

# =============================================================================
# GLOBAL DATA STORAGE
# =============================================================================
# These variables store the main datasets used throughout the application

dashboard_df = None  # Main DataFrame containing merged station and evasion data
realtime_data = []   # List of real-time tap-on records for the last 24 hours
evasion_alerts = []  # List of current evasion alerts requiring attention

# =============================================================================
# DATA LOADING AND PROCESSING FUNCTIONS
# =============================================================================

def load_station_data():
    """
    Load and merge both CSV files into a single comprehensive DataFrame
    
    This function:
    1. Loads expected passenger data from expected.csv
    2. Loads actual tap-on data from sample_tap_on_dataset.csv
    3. Calculates realistic evasion rates based on time patterns
    4. Merges all data into a single dashboard DataFrame
    5. Performs data validation and cleanup
    
    Returns:
        None (modifies global dashboard_df variable)
    """
    global dashboard_df
    
    # Define file paths for data sources
    expected_file = 'data/expected.csv'  # Contains expected passenger volumes and station info
    sample_file = 'data/sample_tap_on_dataset.csv'  # Contains actual tap-on data
    
    # Check if required data files exist
    if not os.path.exists(expected_file) or not os.path.exists(sample_file):
        return  # Exit if data files are missing
    
    try:
        # =================================================================
        # STEP 1: LOAD RAW DATA FROM CSV FILES
        # =================================================================
        
        # Load expected passenger data (contains station info, coordinates, expected volumes)
        expected_df = pd.read_csv(expected_file)
        
        # Load actual tap-on data (contains real tap-on records by time and station)
        sample_df = pd.read_csv(sample_file)
        
        # =================================================================
        # STEP 2: DATA TYPE CONVERSION AND VALIDATION
        # =================================================================
        
        # Convert passenger volume columns to numeric (handle any text/empty values)
        numeric_columns = [
            'Pax_annual',    # Annual passenger count
            'Pax_weekday',   # Average weekday passengers
            'Pax_AM_peak',   # Morning peak passengers
            'Pax_PM_peak',   # Evening peak passengers
            'Pax_Saturday',  # Saturday passengers
            'Pax_Sunday'     # Sunday passengers
        ]
        
        for col in numeric_columns:
            if col in expected_df.columns:
                # Convert to numeric, replacing invalid values with NaN
                expected_df[col] = pd.to_numeric(expected_df[col], errors='coerce')
        
        # Convert coordinate columns to numeric for map plotting
        if 'Stop_lat' in expected_df.columns:
            expected_df['Stop_lat'] = pd.to_numeric(expected_df['Stop_lat'], errors='coerce')
        if 'Stop_long' in expected_df.columns:
            expected_df['Stop_long'] = pd.to_numeric(expected_df['Stop_long'], errors='coerce')
        
        # Convert actual tap-on counts to numeric
        if 'actual' in sample_df.columns:
            sample_df['actual'] = pd.to_numeric(sample_df['actual'], errors='coerce')
        
        # Calculate realistic evasion rates from sample data
        # Create a more sophisticated calculation based on time bins and expected patterns
        evasion_summary = []
        
        for station_name in sample_df['Stop_name'].unique():
            station_data = sample_df[sample_df['Stop_name'] == station_name]
            
            # Calculate expected values based on time bin patterns
            total_actual = station_data['actual'].sum()
            record_count = len(station_data)
            
            # Calculate expected values based on time bin (more realistic)
            expected_by_bin = {
                'pre_AM_peak': 1.1,  # 10% higher than actual (some evasion)
                'AM_peak': 1.15,     # 15% higher (more evasion during peak)
                'interpeak': 1.05,   # 5% higher (less evasion during off-peak)
                'PM_peak': 1.12,     # 12% higher (moderate evasion)
                'PM_late': 1.08      # 8% higher (some evasion)
            }
            
            total_expected = 0
            for _, row in station_data.iterrows():
                time_bin = row['time_bin']
                actual = row['actual']
                multiplier = expected_by_bin.get(time_bin, 1.1)
                expected = actual * multiplier
                total_expected += expected
            
            # Calculate evasion metrics
            total_evasion = max(0, total_expected - total_actual)
            avg_evasion_rate = total_evasion / total_expected if total_expected > 0 else 0.05
            
            # Add some realistic variation based on station characteristics
            # Busier stations tend to have slightly higher evasion rates
            if total_actual > 1000:  # High volume station
                avg_evasion_rate *= random.uniform(1.1, 1.3)
            elif total_actual > 500:  # Medium volume station
                avg_evasion_rate *= random.uniform(0.9, 1.2)
            else:  # Low volume station
                avg_evasion_rate *= random.uniform(0.7, 1.1)
            
            # Cap evasion rate at reasonable levels
            avg_evasion_rate = min(avg_evasion_rate, 0.4)  # Max 40% evasion
            avg_evasion_rate = max(avg_evasion_rate, 0.02)  # Min 2% evasion
            
            evasion_summary.append({
                'Stop_name': station_name,
                'total_actual': total_actual,
                'total_expected': total_expected,
                'total_evasion': total_evasion,
                'avg_evasion_rate': avg_evasion_rate,
                'record_count': record_count
            })
        
        evasion_summary = pd.DataFrame(evasion_summary)
        
        # Merge expected data with evasion data
        dashboard_df = expected_df.merge(evasion_summary, on='Stop_name', how='left')
        
        # Fill missing evasion data with defaults
        dashboard_df['total_actual'] = dashboard_df['total_actual'].fillna(0)
        dashboard_df['total_expected'] = dashboard_df['total_expected'].fillna(dashboard_df['Pax_weekday'] * 16)  # Rough estimate
        dashboard_df['total_evasion'] = dashboard_df['total_evasion'].fillna(0)
        dashboard_df['avg_evasion_rate'] = dashboard_df['avg_evasion_rate'].fillna(0.05)
        dashboard_df['record_count'] = dashboard_df['record_count'].fillna(0)
        
        # Calculate additional metrics
        dashboard_df['daily_avg'] = dashboard_df['Pax_annual'] / 365
        dashboard_df['peak_ratio'] = (dashboard_df['Pax_AM_peak'] + dashboard_df['Pax_PM_peak']) / dashboard_df['Pax_weekday']
        dashboard_df['weekend_ratio'] = (dashboard_df['Pax_Saturday'] + dashboard_df['Pax_Sunday']) / (2 * dashboard_df['Pax_weekday'])
        
        # Fill any remaining NaN values with 0
        dashboard_df = dashboard_df.fillna(0)
        
        # Sort by annual passengers (busiest first)
        dashboard_df = dashboard_df.sort_values('Pax_annual', ascending=False)
        
    except Exception as e:
        # Handle any data loading errors gracefully
        dashboard_df = None

def get_top_stations(limit=10):
    """Get top stations by annual passengers"""
    if dashboard_df is None or len(dashboard_df) == 0:
        return []
    return dashboard_df.head(limit).to_dict('records')

def get_station_stats():
    """Calculate comprehensive dashboard statistics from merged data"""
    if dashboard_df is None or len(dashboard_df) == 0:
        return {
            'total_stations': 0,
            'total_annual_passengers': 0,
            'avg_daily_passengers': 0,
            'busiest_station': '',
            'quietest_station': '',
            'compliance_rate': 0,
            'revenue_impact': 0
        }
    
    # Calculate basic metrics
    total_annual = dashboard_df['Pax_annual'].sum()
    avg_daily = dashboard_df['daily_avg'].mean()
    
    # Calculate compliance rate (actual vs expected passengers)
    total_expected = dashboard_df['total_expected'].sum()
    total_actual = dashboard_df['total_actual'].sum()
    compliance_rate = (total_actual / total_expected) * 100 if total_expected > 0 else 0
    
    # Calculate revenue impact from evasion (assuming $4.50 average fare)
    total_evasion = dashboard_df['total_evasion'].sum()
    revenue_impact = total_evasion * 4.50
    
    return {
        'total_stations': len(dashboard_df),
        'total_annual_passengers': total_annual,
        'avg_daily_passengers': avg_daily,
        'busiest_station': dashboard_df.iloc[0]['Stop_name'] if len(dashboard_df) > 0 else '',
        'quietest_station': dashboard_df.iloc[-1]['Stop_name'] if len(dashboard_df) > 0 else '',
        'compliance_rate': compliance_rate,
        'revenue_impact': revenue_impact
    }

def generate_realtime_data():
    """Generate real-time tap-on data using sample tap-on dataset"""
    global realtime_data, evasion_alerts
    
    if dashboard_df is None or len(dashboard_df) == 0:
        return
    
    realtime_data = []
    evasion_alerts = []
    
    # Load sample tap-on dataset with pandas
    sample_file = 'data/sample_tap_on_dataset.csv'
    
    try:
        if os.path.exists(sample_file):
            sample_df = pd.read_csv(sample_file)
        else:
            return
    except Exception as e:
        return
    
    # Generate data for the last 24 hours using sample data
    now = datetime.now()
    
    for _, station in dashboard_df.iterrows():
        station_name = station['Stop_name']
        
        # Get sample data for this station
        station_sample = sample_df[sample_df['Stop_name'] == station_name]
        if len(station_sample) == 0:
            continue
        
        for hour in range(24):
            timestamp = now - timedelta(hours=23-hour)
            
            # Determine time bin based on hour
            hour_val = timestamp.hour
            if hour_val in [6, 7]:
                time_bin = 'pre_AM_peak'
            elif hour_val in [8, 9]:
                time_bin = 'AM_peak'
            elif hour_val in [10, 11, 12, 13, 14, 15]:
                time_bin = 'interpeak'
            elif hour_val in [16, 17]:
                time_bin = 'PM_peak'
            else:
                time_bin = 'PM_late'
            
            # Get actual tap-ons from sample data
            time_bin_data = station_sample[station_sample['time_bin'] == time_bin]
            if len(time_bin_data) == 0:
                continue  # Skip if no data for this time bin
            
            actual_tapons = int(time_bin_data.iloc[0]['actual'])
            
            # Calculate expected tap-ons based on time of day and station data
            if time_bin in ['AM_peak', 'PM_peak']:
                expected_hourly = (station['Pax_AM_peak'] + station['Pax_PM_peak']) / 4  # 4 peak hours
            elif time_bin == 'pre_AM_peak':
                expected_hourly = station['Pax_AM_peak'] / 2  # 2 pre-peak hours
            elif time_bin == 'interpeak':
                expected_hourly = (station['Pax_weekday'] - station['Pax_AM_peak'] - station['Pax_PM_peak']) / 6  # 6 interpeak hours
            else:  # PM_late
                expected_hourly = station['Pax_PM_peak'] / 2  # 2 late PM hours
            
            expected = int(expected_hourly)
            # Ensure actual doesn't exceed expected (no negative evasion)
            actual_tapons = min(actual_tapons, expected)
            evasion_rate = (expected - actual_tapons) / expected if expected > 0 else 0
            
            record = {
                'station': station_name,
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'expected': expected,
                'actual': actual_tapons,
                'evasion_rate': evasion_rate,
                'hour': timestamp.hour,
                'time_bin': time_bin,
                'expected_fines': (expected - actual_tapons) * 4.50  # $4.50 average fare
            }
            
            realtime_data.append(record)
            
            # Generate alerts for high evasion
            if evasion_rate > 0.15:  # 15% evasion threshold
                evasion_alerts.append({
                    'station': station_name,
                    'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'evasion_rate': evasion_rate,
                    'severity': 'HIGH' if evasion_rate > 0.30 else 'MEDIUM' if evasion_rate > 0.20 else 'LOW',
                    'expected_fines': record['expected_fines']
                })

def get_evasion_analysis():
    """Get top evasion alerts sorted by evasion rate from merged DataFrame"""
    if dashboard_df is None or len(dashboard_df) == 0:
        return []
    
    # Create alerts from the merged DataFrame
    alerts = []
    for _, station in dashboard_df.iterrows():
        if station['avg_evasion_rate'] > 0.1:  # Only stations with >10% evasion
            alert = {
                'station': station['Stop_name'],
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'evasion_rate': station['avg_evasion_rate'],
                'expected_fines': station['total_evasion'] * 250,  # $250 fine per evasion
                'severity': 'high' if station['avg_evasion_rate'] > 0.25 else 'medium' if station['avg_evasion_rate'] > 0.15 else 'low'
            }
            alerts.append(alert)
    
    # Sort by evasion rate (highest first)
    sorted_alerts = sorted(alerts, key=lambda x: x['evasion_rate'], reverse=True)
    return sorted_alerts[:20]  # Top 20 alerts

def get_station_evasion_summary():
    """Get station-level evasion summary from merged DataFrame"""
    if dashboard_df is None or len(dashboard_df) == 0:
        return []
    
    # Create summary from the merged DataFrame
    summary_list = []
    for _, station in dashboard_df.iterrows():
        summary = {
            'station': station['Stop_name'],
            'total_expected': station['total_expected'],
            'total_actual': station['total_actual'],
            'total_evasion': station['total_evasion'],
            'avg_evasion_rate': station['avg_evasion_rate'],
            'alert_count': station['record_count']
        }
        summary_list.append(summary)
    
    # Sort by total evasion (highest first)
    summary_list.sort(key=lambda x: x['total_evasion'], reverse=True)
    
    return summary_list

# =============================================================================
# USER MANAGEMENT FUNCTIONS
# =============================================================================

def load_users():
    """Load users from JSON file"""
    with open('users.json', 'r') as f:
        return json.load(f)

def save_users(users_data):
    """Save users to JSON file"""
    with open('users.json', 'w') as f:
        json.dump(users_data, f, indent=2)

def authenticate_user(username, password):
    """Authenticate user with username and password"""
    users_data = load_users()
    users = users_data.get('users', {})
    
    if username in users:
        user = users[username]
        if user['password'] == password:
            return {
                'username': username,
                'role': user['role'],
                'name': user['name']
            }
    return None

def add_user(username, password, role, name):
    """Add a new user"""
    users_data = load_users()
    users_data['users'][username] = {
        'password': password,
        'role': role,
        'name': name
    }
    save_users(users_data)
    return True

def get_all_users():
    """Get all users"""
    users_data = load_users()
    return users_data.get('users', {})

def delete_user(username):
    """Delete a user"""
    users_data = load_users()
    if username in users_data['users']:
        del users_data['users'][username]
        save_users(users_data)
        return True
    return False

def login_required(f):
    """Decorator to require login for protected routes"""
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page with multi-user support"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = authenticate_user(username, password)
        if user:
            session['logged_in'] = True
            session['username'] = user['username']
            session['user_role'] = user['role']
            session['user_name'] = user['name']
            flash(f'Welcome back, {user["name"]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# =============================================================================
# ADMIN ROUTES FOR USER MANAGEMENT
# =============================================================================

def admin_required(f):
    """Decorator to require admin role"""
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or session.get('user_role') != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """Admin user management page"""
    users = get_all_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
@login_required
@admin_required
def add_user_route():
    """Add new user (admin only)"""
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    name = request.form.get('name')
    
    if not all([username, password, role, name]):
        flash('All fields are required', 'error')
        return redirect(url_for('admin_users'))
    
    # Check if user already exists
    users = get_all_users()
    if username in users:
        flash('Username already exists', 'error')
        return redirect(url_for('admin_users'))
    
    add_user(username, password, role, name)
    flash(f'User {username} added successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/delete/<username>')
@login_required
@admin_required
def delete_user_route(username):
    """Delete user (admin only)"""
    if username == session.get('username'):
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('admin_users'))
    
    if delete_user(username):
        flash(f'User {username} deleted successfully', 'success')
    else:
        flash('User not found', 'error')
    
    return redirect(url_for('admin_users'))

@app.route('/')
@login_required
def index():
    """Main dashboard page"""
    # Ensure data is loaded
    if dashboard_df is None or len(dashboard_df) == 0:
        load_station_data()
    
    # Generate real-time data first
    generate_realtime_data()
    
    # Get dashboard data
    stats = get_station_stats()
    top_stations = get_top_stations(10)
    evasion_analysis = get_evasion_analysis()
    evasion_summary = get_station_evasion_summary()
    
    # Calculate key metrics for dashboard display
    total_evasion = dashboard_df['total_evasion'].sum() if dashboard_df is not None and 'total_evasion' in dashboard_df.columns else 0
    high_risk_stations = len(dashboard_df[dashboard_df['avg_evasion_rate'] > 0.15]) if dashboard_df is not None and 'avg_evasion_rate' in dashboard_df.columns else 0
    active_alerts = len(evasion_analysis) if evasion_analysis else 0
    
    # Prepare data for charts and display
    chart_data = evasion_summary[:10] if evasion_summary else []
    data_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Create station coordinates dictionary for the map using pandas
    station_coordinates = {}
    if dashboard_df is not None and 'Stop_lat' in dashboard_df.columns and 'Stop_long' in dashboard_df.columns:
        for _, station in dashboard_df.iterrows():
            try:
                station_coordinates[station['Stop_name']] = {
                    'lat': float(station['Stop_lat']),
                    'lng': float(station['Stop_long'])
                }
            except (ValueError, KeyError) as e:
                continue
    
    return render_template('index.html', 
                         stats=stats,
                         top_stations=top_stations,
                         evasion_analysis=evasion_analysis,
                         evasion_summary=evasion_summary,
                         chart_data=chart_data,
                         total_evasion=total_evasion,
                         high_risk_stations=high_risk_stations,
                         active_alerts=active_alerts,
                         all_stations=dashboard_df.to_dict('records') if dashboard_df is not None else [],
                         station_coordinates=station_coordinates,
                         data_timestamp=data_timestamp)

@app.route('/api/stations')
def api_stations():
    """API endpoint to get station data"""
    return jsonify(dashboard_df.to_dict('records') if dashboard_df is not None else [])

@app.route('/api/stats')
def api_stats():
    """API endpoint to get statistics"""
    # Generate real-time data first
    generate_realtime_data()
    return jsonify(get_station_stats())

@app.route('/api/realtime')
def api_realtime():
    """API endpoint to get real-time data"""
    return jsonify({
        'realtime_data': realtime_data[-100:],  # Last 100 records
        'evasion_alerts': evasion_alerts[-20:],  # Last 20 alerts
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/evasion-summary')
def api_evasion_summary():
    """API endpoint to get evasion summary"""
    return jsonify(get_station_evasion_summary())

@app.route('/api/routes')
def api_routes():
    """API endpoint to get routes data in Figma format"""
    evasion_summary = get_station_evasion_summary()
    if not evasion_summary:
        return jsonify({'data': []})
    
    routes = []
    for i, station in enumerate(evasion_summary[:20]):  # Top 20 stations
        # Determine route type based on station name patterns
        station_name = station['station'].lower()
        if any(keyword in station_name for keyword in ['central', 'flinders', 'southern cross', 'parliament', 'melbourne central']):
            route_type = 'train'
        elif any(keyword in station_name for keyword in ['bus', 'interchange']):
            route_type = 'bus'
        else:
            route_type = 'tram'
        
        # Calculate expected fines (simplified)
        expected_fines = int(station['total_evasion'] * 0.1)  # Assume 10% of evaders get fined
        
        routes.append({
            'id': f'route_{i+1}',
            'name': station['station'],
            'type': route_type,
            'nonComplianceRate': round(station['avg_evasion_rate'] * 100, 1),
            'avgDailyPassengers': station['total_expected'],
            'expectedFines': expected_fines,
            'peakHours': '7-9 AM, 5-7 PM',
            'riskLevel': 'high' if station['avg_evasion_rate'] > 0.6 else 'medium' if station['avg_evasion_rate'] > 0.3 else 'low'
        })
    
    return jsonify({'data': routes})

if __name__ == '__main__':
    # Load station data on startup
    load_station_data()
    
    # Start Flask development server
    app.run(debug=True, host='0.0.0.0', port=5000)
