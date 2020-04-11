from django.urls import path, include
from . import views

app_name = 'goods'

urlpatterns = [
    path(r'index/', views.IndexView.as_view(), name="index"),   # 首页
    path(r'goods/<str:goods_id>', views.DetailView.as_view(), name='detail'),  # 详情页
    path(r'list/<int:type_id>/<int:page>', views.ListView.as_view(), name='list'),  # 列表页
]
