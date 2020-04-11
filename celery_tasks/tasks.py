# celery任务

import time
import subprocess

# 在任务处理者一端加入这几行代码
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dailyfresh.settings')
django.setup()

from celery import Celery
from dailyfresh import settings
from django.core.mail import send_mail
from django.template import loader
from goods.models import *


# 创建一个Celery类的实例对象,8是数据库
app = Celery('celery_task.tasks', broker='redis://:inops123456@192.168.88.139:6379/8')


# 定义任务函数
@app.task
def send_register_active_email(to_email, username, token):
    """发送激活邮件"""
    # 组织邮件信息
    subject = "天天生鲜欢迎信息"
    message = ''
    host = settings.HOST
    http_message = '<h1>{}, 欢迎您成为天天生鲜注册会员<h1>请点击下面链接激活您的账户<br/><a href="http://{}:8000/' \
                   'user/active/{}">http://{}:8000/user/active/{}<a>'.format(username, host, token, host, token)
    sender = settings.EMAIL_FROM
    receiver = [to_email]
    # 如果有html元素，需要使用html_message参数
    # send_mail在发送到smtp服务器时，可能会有网络延迟，smtp服务器发送到用户也可能会延迟
    send_mail(subject=subject, message=message, from_email=sender, recipient_list=receiver, html_message=http_message)
    time.sleep(5)


@app.task
def generate_static_index_html():
    """生成首页静态页面"""
    types = GoodsType.objects.all()

    # 获取轮播图
    goods_banners = IndexGoodsBanner.objects.all().order_by('index')

    # 获取促销活动
    promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

    # 获取商品分类
    type_goods = IndexTypeGoodsBanner.objects.all()
    for type in types:
        title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0)
        image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1)
        # 给type增加属性
        type.title_banners = title_banners
        type.image_banners = image_banners

    # 使用模板
    # １．加载模板
    template = loader.get_template('index_static.html')
    # 2．模板渲染
    static_index_html = template.render(locals())

    # 生成静态页面
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')

    with open(save_path, 'w') as f:
        f.write(static_index_html)
