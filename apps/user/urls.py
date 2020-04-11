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
from django.urls import path
from . import views

app_name = 'user'

urlpatterns = [
    path(r'register/', views.RegisterView.as_view(), name='register'),  # 注册
    path(r'active/<str:token>', views.ActiveView.as_view(), name='active'),  # 用户激活
    path(r'login/', views.LoginView.as_view(), name='login'),  # 用户登录
    path(r'logout/', views.LogoutView.as_view(), name='logout'),  # 用户退出
    path(r'order/<int:page>', views.UserOrderView.as_view(), name='order'),   # 用户订单
    path(r'address/', views.AddressView.as_view(), name='address'),   # 用户地址页
    path(r'', views.UserInfoView.as_view(), name='user'),   # 用户信息页
]
