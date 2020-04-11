"""dailyfresh URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include


from .views import OrderPlaceView, OrderCommitView, OrderPayVIew, OrderCheckView
from goods.views import CommentView

app_name = 'order'

urlpatterns = [
    path('place', OrderPlaceView.as_view(), name="place"),  # 提交订单页面显示
    path('commit', OrderCommitView.as_view(), name="commit"),    # 订单创建
    path('pay', OrderPayVIew.as_view(), name="pay"),     # 订单支付
    path('check', OrderCheckView.as_view(), name="check"),     # 支付结果查询
    path('comment/<str:order_id>', CommentView.as_view(), name="comment"),     # 订单评价
]
