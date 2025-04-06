from flask import Flask, render_template, session, redirect, url_for, request
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_visualizer_secret_key'
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Initialize Firebase only if not already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate('firebase.json')
    firebase_admin.initialize_app(cred)

db = firestore.client()


@app.template_filter('format_date')
def format_date(value, format='%b %d, %Y'):
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return value.strftime(format)


def get_user_data():
    """Retrieve and process all user data"""
    users_ref = db.collection('users')
    users = []

    for user in users_ref.stream():
        user_data = user.to_dict()
        user_data['id'] = user.id
        sessions = user_data.get('sessions', [])

        user_data['total_sessions'] = len(sessions)
        user_data['total_reps'] = sum(session.get('count', 0) for session in sessions)
        user_data['last_active'] = max(
            (datetime.strptime(session['date'], '%Y-%m-%d %H:%M:%S') for session in sessions),
            default=None
        )
        users.append(user_data)

    return pd.DataFrame(users) if users else pd.DataFrame(
        columns=['id', 'username', 'total_sessions', 'total_reps', 'last_active'])


def create_visualizations(df):
    """Generate interactive visualizations"""
    if df.empty:
        return {'heatmap': '', 'performance': '', 'user_stats': ''}

    all_sessions = []
    for _, user in df.iterrows():
        for session in user.get('sessions', []):
            session_date = datetime.strptime(session['date'], '%Y-%m-%d %H:%M:%S').date()
            all_sessions.append({'date': session_date, 'user': user['username'], 'count': session['count']})

    sessions_df = pd.DataFrame(all_sessions)
    if sessions_df.empty:
        return {'heatmap': '', 'performance': '', 'user_stats': ''}

    heatmap_data = sessions_df.pivot_table(index='date', columns='user', values='count', aggfunc='sum', fill_value=0)
    heatmap_fig = px.imshow(heatmap_data, labels=dict(x='User', y='Date', color='Repetitions'), aspect='auto')
    heatmap_fig.update_layout(title='Daily Activity Heatmap')

    performance_df = sessions_df.groupby('date').agg(total_reps=('count', 'sum'),
                                                     session_count=('count', 'count')).reset_index()
    performance_fig = make_subplots(specs=[[{"secondary_y": True}]])
    performance_fig.add_trace(
        go.Scatter(x=performance_df['date'], y=performance_df['total_reps'], name="Total Reps", mode='lines+markers'))
    performance_fig.add_trace(
        go.Bar(x=performance_df['date'], y=performance_df['session_count'], name="Sessions", opacity=0.5),
        secondary_y=True)
    performance_fig.update_layout(title='Performance Trends', xaxis_title='Date', yaxis_title='Repetitions')

    stats_fig = px.bar(df.nlargest(10, 'total_reps'), x='username', y='total_reps', color='total_sessions',
                       title='Top 10 Users by Total Repetitions')

    return {
        'heatmap': heatmap_fig.to_html(full_html=False),
        'performance': performance_fig.to_html(full_html=False),
        'user_stats': stats_fig.to_html(full_html=False)
    }


@app.route('/')
def dashboard():
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin_login'))

    df = get_user_data()
    visualizations = create_visualizations(df)

    stats = {
        'total_users': len(df),
        'active_users': len(df[df['total_sessions'] > 0]),
        'total_reps': df['total_reps'].sum() if not df.empty else 0,
        'avg_reps': round(df['total_reps'].mean(), 1) if not df.empty and df['total_reps'].sum() > 0 else 0
    }

    recent_sessions = df[['username', 'last_active', 'total_sessions']].dropna().sort_values('last_active',
                                                                                             ascending=False).head(
        5).to_dict(orient='records')

    return render_template('dashboard.html', stats=stats, recent_activity=recent_sessions,
                           visualizations=visualizations, now=datetime.now())


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == 'securepassword':
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
        return render_template('admin_login.html', error="Invalid credentials")

    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


if __name__ == '__main__':
    app.run(port=5001, debug=True)
