"""Created originally by Ethan Chiu 10/25/16
v2.0.0 created on 8/4/18
Complete redesign for efficiency and scalability
Uses Python 3 now

v2.1.0 created on 5/10/19
Improve efficiency and design
 """
from ctpbee import current_app as bee_current_app
from app.pylint_lib import pylint_dict_final
from flask import request, session
import tempfile, mmap, os, re
from datetime import datetime
from pylint import epylint as lint
from subprocess import Popen, PIPE, STDOUT
from multiprocessing import Pool, cpu_count

from flask.views import MethodView
from app.auth import auth_required
from app.global_var import G
from app.default_settings import true_response, false_response
from app.strategy_lib import add_strategy, get_strategy, delete_strategy

is_linux = True

if os.name == "nt":
    is_linux = False

# Get number of cores for multiprocessing
num_cores = cpu_count()


# Slow down if user clicks "Run" too many times
def evaluate_pylint(text):
    """Create temp files for pylint parsing on user code

    :param text: user code
    :return: dictionary of pylint errors:
        {
            {
                "code":...,
                "error": ...,
                "message": ...,
                "line": ...,
                "error_info": ...,
            }
            ...
        }
    """
    # Open temp file for specific session.
    # IF it doesn't exist (aka the key doesn't exist), create one
    se = G.session[session['token']]
    try:
        se["file_name"]
        f = open(se["file_name"], "w")
        for t in text:
            f.write(t)
        f.flush()
    except Exception as e:
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            se["file_name"] = temp.name
            for t in text:
                temp.write(t.encode("utf-8"))
            temp.flush()

    try:
        ARGS = " -r n --disable=R,C"
        (pylint_stdout, pylint_stderr) = lint.py_run(
            se["file_name"] + ARGS, return_std=True)
    except Exception as e:
        raise Exception(e)

    if pylint_stderr.getvalue():
        raise Exception("Issue with pylint configuration")

    return format_errors(pylint_stdout.getvalue())


def process_error(error):
    """Formats error message into dictionary

        :param error: pylint error full text
        :return: dictionary of error as:
            {
                "code":...,
                "error": ...,
                "message": ...,
                "line": ...,
                "error_info": ...,
            }
    """
    # Return None if not an error or warning
    if error == " " or error is None:
        return None
    if error.find("Your code has been rated at") > -1:
        return None

    list_words = error.split()
    if len(list_words) < 3:
        return None

    # Detect OS
    line_num = None
    if is_linux:
        try:
            line_num = error.split(":")[1]
        except Exception as e:
            print(os.name + " not compatible: " + e)
    else:
        line_num = error.split(":")[2]

    # list_words.pop(0)
    error_yet, message_yet, first_time = False, False, True
    i, length = 0, len(list_words)
    # error_code=None
    while i < length:
        word = list_words[i]
        if (word == "error" or word == "warning") and first_time:
            error_yet = True
            first_time = False
            i += 1
            continue
        if error_yet:
            error_code = word[1:-1]
            error_string = list_words[i + 1][:-1]
            i = i + 3
            error_yet = False
            message_yet = True
            continue
        if message_yet:
            full_message = ' '.join(list_words[i:length - 1])
            break
        i += 1

    error_info = pylint_dict_final[error_code]

    return {
        "code": error_code,
        "error": error_string,
        "message": full_message,
        "line": line_num,
        "error_info": error_info,
    }


def format_errors(pylint_text):
    """Format errors into parsable nested dictionary

    :param pylint_text: original pylint output
    :return: dictionary of errors as:
        {
            {
                "code":...,
                "error": ...,
                "message": ...,
                "line": ...,
                "error_info": ...,
            }
            ...
        }
    """
    errors_list = pylint_text.splitlines(True)

    # If there is not an error, return nothing
    if "--------------------------------------------------------------------" in errors_list[1] and \
            "Your code has been rated at" in errors_list[2] and "module" not in errors_list[0]:
        return None

    errors_list.pop(0)

    pylint_dict = {}
    try:
        pool = Pool(num_cores)
        pylint_dict = pool.map(process_error, errors_list)
    finally:
        pool.close()
        pool.join()
        return pylint_dict

    # count = 0
    # for error in errors_list:
    #     pylint_dict[count]=process_error(error)
    #     count +=1
    # return pylint_dict


class CheckCode(MethodView):
    @auth_required
    def post(self):
        """Run pylint on code and get output
            :return: JSON object of pylint errors
                {
                    {
                        "code":...,
                        "error": ...,
                        "message": ...,
                        "line": ...,
                        "error_info": ...,
                    }
                    ...
                }

            For more customization, please look at Pylint's library code:
            https://github.com/PyCQA/pylint/blob/master/pylint/lint.py
        """
        # Session to handle multiple users at one time and to get textarea from AJAX call
        se = G.session[session['token']]

        se["code"] = request.form['text']
        text = se["code"]
        output = evaluate_pylint(text)
        print(output)
        # MANAGER.astroid_cache.clear()
        return true_response(data=output)


def slow():
    se = G.session[session['token']]
    se["count"] += 1
    time = datetime.now() - se["time_now"]
    if float(se["count"]) / float(time.total_seconds()) > 5:
        return True
    return False


# Run python in secure system
class RunCode(MethodView):
    """Run python 3 code
        :return: JSON object of python 3 output
            {
                ...
            }
    """

    # Don't run too many times
    @auth_required
    def post(self):
        if slow():
            return false_response(msg=
                                  "Running code too much within a short time period. "
                                  "Please wait a few seconds Run .")
        se = G.session[session['token']]
        se["time_now"] = datetime.now()
        se["code"] = request.form['text']
        text = se['code']
        try:
            se["file_name"]
            f = open(se["file_name"], "w")
            for t in text:
                f.write(t)
            f.flush()
        except Exception as e:
            with tempfile.NamedTemporaryFile(delete=False) as temp:
                se["file_name"] = temp.name
                for t in text:
                    temp.write(t.encode("utf-8"))
                temp.flush()
        output = None
        cmd = 'python ' + se["file_name"]
        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE,
                  stderr=STDOUT, close_fds=True)
        output = p.stdout.read()

        return true_response(data=output.decode('utf-8'))


class CodeManage(MethodView):
    @auth_required
    def get(self):
        name = request.values.get('name')
        if name and name != 'default_settings':
            text = get_strategy(name)
            if text:
                return true_response(data=text)
            else:
                return false_response(msg='unknown name')
        return false_response(msg='name is none')

    @auth_required
    def post(self):
        pattern = r"ext\s*=\s*\w*[(][\"\'](.*)[\"\'][)]"
        se = G.session[session['token']]

        text = request.values.get('text')
        name = re.findall(pattern, text)  # 检测 name ,ext
        if not name or not text:
            return false_response(msg='name,text为空 or 未定义ext变量 ')
        name = name[-1]
        res = add_strategy(name, text)
        if res is True:
            return true_response(msg='添加成功')
        else:
            return false_response(msg='添加失败:' + res)


class StrategyView(MethodView):
    @auth_required
    def get(self):
        G.session = dict(token=session['token'], data=dict(count=0, time_now=datetime.now()))
        result = []
        for k, v in bee_current_app.extensions.items():
            temp = {}
            temp['name'] = k
            temp['status'] = "停止" if v.frozen else "运行中"
            result.append(temp)
        return true_response(data=result)

    @auth_required
    def put(self):
        operation = request.values.get('operation')
        name = request.values.get('name')
        if name in bee_current_app.extensions:
            if operation == "开启":
                res = bee_current_app.enable_extension(name)
            elif operation == "关闭":
                res = bee_current_app.suspend_extension(name)
            else:
                res = 'unknown'
            res = '成功' if res is True else '失败'
            return true_response(msg=f'{operation} {name} {res}')
        return false_response(msg=f"{name} not found！")

    @auth_required
    def delete(self):
        name = request.values.get('name')
        if delete_strategy(name):
            return true_response(msg=f'删除{name}成功')
        return false_response(msg=f'删除{name}失败')
