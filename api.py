from flask import Flask, request, jsonify
from flask_cors import CORS
from database import SessionLocal, User, QuestionPaper
from config import TOKEN
import hashlib
import hmac
import json
import os
from functools import wraps

app = Flask(__name__)
CORS(app)

def verify_telegram_data(init_data):
    """Verify that the data is coming from Telegram"""
    try:
        received_hash = init_data.get('hash', '')
        data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(init_data.items()) if k != 'hash')
        secret_key = hmac.new('WebAppData'.encode(), TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return calculated_hash == received_hash
    except Exception:
        return False

def telegram_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data')
        if not init_data or not verify_telegram_data(json.loads(init_data)):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/user', methods=['GET'])
@telegram_auth_required
def get_user():
    init_data = json.loads(request.headers.get('X-Telegram-Init-Data'))
    user_id = init_data.get('user', {}).get('id')
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    
    if not user:
        user = User(telegram_id=user_id, stars=0)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    response = {
        'id': user.telegram_id,
        'first_name': init_data.get('user', {}).get('first_name'),
        'stars': user.stars
    }
    
    db.close()
    return jsonify(response)

@app.route('/api/departments', methods=['GET'])
def get_departments():
    db = SessionLocal()
    departments = db.query(QuestionPaper.department).filter(
        QuestionPaper.department != "",
        ~QuestionPaper.department.startswith("__")
    ).distinct().all()
    db.close()
    
    return jsonify([d[0] for d in departments])

@app.route('/api/semesters/<department>', methods=['GET'])
def get_semesters(department):
    db = SessionLocal()
    semesters = db.query(QuestionPaper.semester).filter(
        QuestionPaper.department == department,
        QuestionPaper.semester != ""
    ).distinct().all()
    db.close()
    
    return jsonify([s[0] for s in semesters])

@app.route('/api/years/<department>/<semester>', methods=['GET'])
def get_years(department, semester):
    db = SessionLocal()
    years = db.query(QuestionPaper.year).filter(
        QuestionPaper.department == department,
        QuestionPaper.semester == semester,
        QuestionPaper.year != ""
    ).distinct().all()
    db.close()
    
    return jsonify([y[0] for y in years])

@app.route('/api/papers/<department>/<semester>/<year>', methods=['GET'])
def get_papers(department, semester, year):
    db = SessionLocal()
    papers = db.query(QuestionPaper).filter(
        QuestionPaper.department == department,
        QuestionPaper.semester == semester,
        QuestionPaper.year == year,
        ~QuestionPaper.paper_name.in_(["__DEPT__", "__SEM__", "__YEAR__"])
    ).all()
    db.close()
    
    return jsonify([{
        'id': paper.id,
        'paper_name': paper.paper_name,
        'price': paper.price
    } for paper in papers])

@app.route('/api/purchase', methods=['POST'])
@telegram_auth_required
def purchase_paper():
    init_data = json.loads(request.headers.get('X-Telegram-Init-Data'))
    user_id = init_data.get('user', {}).get('id')
    paper_id = request.json.get('paperId')
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    paper = db.query(QuestionPaper).filter(QuestionPaper.id == paper_id).first()
    
    if not user or not paper:
        db.close()
        return jsonify({'success': False, 'message': 'User or paper not found'})
    
    if paper in user.purchased_papers:
        db.close()
        return jsonify({'success': False, 'message': 'You have already purchased this paper'})
    
    if user.stars >= paper.price:
        user.stars -= paper.price
        user.purchased_papers.append(paper)
        db.add(user)
        db.commit()
        db.close()
        return jsonify({'success': True, 'requiresPayment': False})
    else:
        db.close()
        return jsonify({
            'success': True,
            'requiresPayment': True,
            'requiredStars': paper.price
        })

@app.route('/api/create-invoice', methods=['POST'])
@telegram_auth_required
def create_invoice():
    init_data = json.loads(request.headers.get('X-Telegram-Init-Data'))
    user_id = init_data.get('user', {}).get('id')
    amount = request.json.get('amount')
    
    # Here you would integrate with your payment provider
    # For now, we'll return a mock invoice URL
    invoice_url = f"https://t.me/your_bot?start=pay_{amount}_{user_id}"
    
    return jsonify({'invoiceUrl': invoice_url})

@app.route('/api/purchase-history', methods=['GET'])
@telegram_auth_required
def get_purchase_history():
    init_data = json.loads(request.headers.get('X-Telegram-Init-Data'))
    user_id = init_data.get('user', {}).get('id')
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    
    if not user:
        db.close()
        return jsonify([])
    
    history = [{
        'paper_id': paper.id,
        'paper_name': paper.paper_name,
        'department': paper.department,
        'semester': paper.semester,
        'year': paper.year,
        'purchase_date': paper.purchase_date.isoformat() if hasattr(paper, 'purchase_date') else None
    } for paper in user.purchased_papers[-10:]]  # Get last 10 purchases
    
    db.close()
    return jsonify(history)

@app.route('/api/profile', methods=['GET'])
@telegram_auth_required
def get_profile():
    init_data = json.loads(request.headers.get('X-Telegram-Init-Data'))
    user_id = init_data.get('user', {}).get('id')
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    
    if not user:
        db.close()
        return jsonify({'error': 'User not found'}), 404
    
    # Calculate statistics
    total_papers = len(user.purchased_papers)
    total_spent = sum(paper.price for paper in user.purchased_papers)
    
    # Department-wise statistics
    dept_stats = {}
    for paper in user.purchased_papers:
        if paper.department not in dept_stats:
            dept_stats[paper.department] = 0
        dept_stats[paper.department] += 1
    
    response = {
        'total_papers': total_papers,
        'total_spent': total_spent,
        'department_stats': dept_stats
    }
    
    db.close()
    return jsonify(response)

@app.route('/api/request-paper/<int:paper_id>', methods=['GET'])
@telegram_auth_required
def request_paper(paper_id):
    init_data = json.loads(request.headers.get('X-Telegram-Init-Data'))
    user_id = init_data.get('user', {}).get('id')
    
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    paper = db.query(QuestionPaper).filter(QuestionPaper.id == paper_id).first()
    
    if not user or not paper:
        db.close()
        return jsonify({'success': False, 'message': 'User or paper not found'})
    
    if paper not in user.purchased_papers:
        db.close()
        return jsonify({'success': False, 'message': 'You have not purchased this paper'})
    
    db.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True) 