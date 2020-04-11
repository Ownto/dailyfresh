# Create your views here.
import re

from django.shortcuts import render, redirect
from django.http.response import HttpResponse
from django.urls import reverse
from django.views.generic import View
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator


from dailyfresh import settings
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from django_redis import get_redis_connection


from celery_tasks.tasks import send_register_active_email
from .models import User, Address
from goods.models import GoodsSKU
from order.models import OrderGoods, OrderInfo
from utils.mixin import LoginRequiredMixin


__all__ = ['RegisterView', 'ActiveView', 'LoginView', 'UserInfoView', 'UserOrderView', 'AddressView', 'LogoutView']


class RegisterView(View):
    def get(self, request):
        # 显示注册页面
        return render(request, 'user/register.html')

    def post(self, request):
        # 接收数据
        username = request.POST.get('user_name')
        pwd = request.POST.get('pwd')
        cpwd = request.POST.get('cpwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')
        # 进行数据校验
        if not all([username, pwd, email]):
            # 数据不完整
            return render(request, 'user/register.html', {'errmsg': '数据不完整'})

        if not re.match(r'^[a-z0-9][\w.-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            # 邮箱格式不正确
            return render(request, 'user/register.html', {'errmsg': '邮箱格式不正确'})

        if cpwd != pwd:
            # 两次密码不一致
            return render(request, 'user/register.html', {'errmsg': '两次密码不一致'})

        if allow != 'on':
            # 没有同意协议
            return render(request, 'user/register.html', {'errmsg': '请同意协议'})

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None

        if user:
            # 用户名存在
            return render(request, 'user/register.html', {'errmsg': '用户名已存在'})

        # 进行业务处理：进行用户注册
        user = User.objects.create_user(username, email, pwd)
        user.is_active = 0
        user.save()

        # 发送激活邮件，包含激活链接：http://127.0.0.1:8000/user/active/1
        # 激活链接中需要包含用户的身份信息（user id），并且要把身份信息进行加密
        # 为了防止激活链接被暴力破解，需要对用户ID进行加密

        # 加密用户的身份信息，生产激活的token
        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        # info必须是个字典
        token = serializer.dumps(info)  # bytes
        token = token.decode('utf-8')   # str
        # 发送邮件
        send_register_active_email.delay(email, username, token)
        # 返回应答
        return redirect(reverse('goods:index'))


class ActiveView(View):
    """用户激活"""
    def get(self, request, token):
        # 进行解密，获取激活的用户信息
        serializer = Serializer(settings.SECRET_KEY, 3600)
        try:
            info = serializer.loads(token)
            user_id = info['confirm']
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()

            # 跳转到登录页面
            return redirect(reverse('user:login'))
        except SignatureExpired as e:
            # 激活链接已过期
            return HttpResponse('激活链接已过期')


class LoginView(View):
    """用户登录"""
    def get(self, request):
        """显示登录页面"""
        # 判断是否记住用户名
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''
        return render(request, 'user/login.html', locals())

    def post(self, request):
        """登录校验"""
        # 接收数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')

        # 校验数据
        # all()接收一个可迭代对象，如果对象里的所有元素的bool运算值都是True，那么返回True，否则False。
        if not all([username, password]):
            return render(request, 'user/login.html', {'errmsg': '数据不完整'})
        # 业务处理：登录校验
        user = authenticate(username=username, password=password)
        if user is not None:
            # 用户名密码正确
            if user.is_active:
                # 用户已激活
                login(request, user)
                # redirect()返回一个HttpResponseRedirect对象，是HttpResponse的一个子类
                response = redirect(reverse('goods:index'))
                # 判断是否需要记住用户名
                remember = request.POST.get('remember')
                if remember == "on":
                    # 记住用户名，需要一个cookice
                    response.set_cookie('username', username, max_age=7*24*3600)
                else:
                    response.delete_cookie('username')

                # 返回response
                return response
            else:
                return render(request, 'user/login.html', {'errmsg': "用户未激活"})
        else:
            # 用户名或者密码错误
            return render(request, 'user/login.html', {'errmsg': "用户名或者密码错误"})


class LogoutView(View):

    def get(self, request):
        logout(request)
        return redirect(reverse('goods:index'))


class UserInfoView(LoginRequiredMixin, View):
    """用户中心－信息页"""

    def get(self, request):

        # request.user.is_authenticated()
        # request.user
        # 如果用户未登录-> AnonymousUser类的一个实例
        # 如果用户登录-> User类的一个实例
        # 除了你给模板文件传递的模板变量之外，django框架会把request.user也传递给模板文件

        # 获取个人信息
        user = request.user
        address = Address.objects.get_default_address(user=user)

        # 获取redis数据库连接, 'default' == setting.CACHE里的default参数
        con = get_redis_connection('default')
        history_key = "history_" + str(user.id)
        # 获取用户浏览记录里的前5个商品sku_id,redis存储方式是list
        sku_ids = con.lrange(history_key, 0, 4)

        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            goods_li.append(goods)

        context = {'address': address,
                   'goods_li': goods_li
                   }

        return render(request, 'user/user_center_info.html', context=context)


class UserOrderView(LoginRequiredMixin, View):
    """用户中心－订单页"""

    def get(self, request, page):
        """显示"""
        # 获取用户的订单信息
        user = request.user
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')
        # 遍历获取订单商品信息
        for order in orders:
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)
            # 遍历order_skus计算商品小计
            for order_sku in order_skus:
                amount = order_sku.count * order_sku.price
                order_sku.amount = amount

            # 动态给order增加属性，保存订单商品信息
            order.order_skus = order_skus

        # 分页
            paginator = Paginator(orders, 1)
        # 获取第page页的内容
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取第page页的Page实例对象
        order_page = paginator.page(page)

        # todo: 进行页码控制，页面上最多显示5个页码
        # 1.总页数小于5页，页面上显示所有页码
        # 2.如果当前页是前3页，显示1-5页
        # 3.如果当前页是后3页，显示后5页
        # 4.其他情况，显示当前页的前2页，当前页，当前页的后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page -2 , page + 3)

        # 组织上下文
        context = {'pages': pages, 'order_page': order_page, 'page': 'order'}
        return render(request, 'user/user_center_order.html', context=context)


class AddressView(LoginRequiredMixin, View):
    """用户中心－地址页"""

    def get(self, request):
        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     address = None

        # 自定义管理器封装方法（获取默认收货地址）
        address = Address.objects.get_default_address(user=user)

        context = {'address': address}

        return render(request, 'user/user_center_site.html', context=context)

    def post(self, request):
        """地址添加"""
        # 接受数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('address')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')
        # 校验数据
        if not all([receiver, addr, phone]):
            return render(request, 'user/user_center_site.html', {'errMsg': '数据不完整'})
        if not re.match(r'^1[3|4|5||7|8][0-9]{9}$', phone):
            return render(request, 'user/user_center_site.html', {'errMsg': '手机格式不正确'})
        # 业务处理
        # 如果用户已存在默认收货地址，添加的地址不作为默认收货地址，否则作为默认收货地址
        # 获取登录用户对应的User对象
        user = request.user
        # 自定义的模型管理器
        address = Address.objects.get_default_address(user=user)

        if address:
            is_default = False
        else:
            is_default = True
        # 添加地址
        Address.objects.create(user=user, addr=addr, receiver=receiver,
                               zip_code=zip_code, phone=phone, is_default=is_default)

        # 返回应答，刷新地址页面
        return redirect(reverse('user:address'))  # get请求方式
