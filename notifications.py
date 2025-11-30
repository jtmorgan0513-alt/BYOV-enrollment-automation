import io
import os
import zipfile
import mimetypes
import smtplib
import json
import requests
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formatdate
from datetime import datetime

import streamlit as st
import file_storage


def get_sears_html_template(record, include_logo=True):
    """Generate a branded HTML email template with Sears styling."""
    
    industries_list = record.get('industry', record.get('industries', []))
    industries_str = ", ".join(industries_list) if industries_list else "None"
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y at %I:%M %p")
        except Exception:
            pass
    
    logo_section = ""
    if include_logo:
        logo_base64 = "iVBORw0KGgoAAAANSUhEUgAAAXMAAACICAMAAAAiRvvOAAADAFBMVEUAAADm///e/f/d9//Y8P/V7//U6v7O7/7L4/7I4f7A1/7B//O+1/660vy2zfWyzfuzzfux//W7//Onvuyhv/mguOSZtvGhuOeZuPi1/+iNq++Rqt2wuN6z/euGo+WKotWBn9l3md98mc52nu+b//Rvjshyk9d+lMOy9dhrnP5pi89mhb1gg86Z/eWR+/BifbJbfrtbf8RXgdRWerJSeMGi99BMccFQcq9IaadJa7Gg9Ns+ZrGP99w4cNNDabtGaKdEZaCW9siB9uxAZKs3X7M8YKGJ99FpdZg0Wqk3WJae7MMyWKAvX70vWKyP9L0wVpcqUp8uVKcuVJQoS4h389Rq8/CE6st07eN58MWI67Rq89Z68bRx96uB675U+PFk/qVN/uBS/dhf/rBp9Mho97to+qpZ/cFc/blg/qld+clC/vZT/shN/9FI+/JV+89V/7pg/51O/8td/6Na/6pJ/9ZR/8Fl+6E7/v1g9M9X/rJo9bND/epJ/808/+9t7NBB/+FH/dpT9Og6/vVf9b5K+9Ne7uE6/+dC/tZI/sZz7qcz//Yz/vtS+MNr68E5/OxU89E0/fFQ8OBG8+okTqImTJYJUMoaSqwRTLgNSsQET8EJTL0RSrEJS7cCTb0OR7wFSccaRpwMSqwTSKMDSsILSLQBTLkCTLQJRsAFSbseRJIQRLYXR5EBSb4BSbkFR7gIRboJQsUDSqsPRKgFRb0LRa0CSbAHR60HRrICRcQRQqwBRr8AR7wMQ7EGRbYASLYAR7oVRogIQrwBR7MJRagQQ58GR6QFQsAKQbUHQrcERa8cQIgBRbUBRLkTP6MXP5YKQ6MBRLIBQrwOQpkAQ7cKQKsQQZUCRKoLQKYIQ54JPrEDQa0BQbICP7kWPY4DQqUaPX0MO6oOPJwHPqEHP5sBPbUOOqICPqkHP5YQOpgOPYsGPKUCPK8OO5MHPJ4TOoQJO5kIO5EFOaIQNpAMN5UHN50QNooDOZcFOIwKNoUGNZIPM4IHMpcHMowLMXsPL3AFL4XbM5uEAAAAlHRSTlMABAcLEBMXGh8kKzAwNjs+QkROT1FWWVxcYGhpanR0dX1/f4CFi4yRk5abnp6ipqmpqqyusbO8vMHFx8fIycjJyczX2djb3N3d4OLm6ejr6u7z8v3+/v/+/////////v/////////////////////////////////////////////////////////////////////+rFuMKgAAO+5JREFUeNrs1j2L2zAYB3C5zsVJQ644JpQjZGrW817IdJ+gw+UCGYzNbSYKHARUUBXJwi9H3D6W/cH6Ybp1q8UtR6eGszvpp5dNy5+H5xEy3shyVwEFvPFdCxn/w8jfZglmGAdJtvUnyOib4++yum4oAwCGmzrzbWT0arWrBKeU5jkwqRSLcbBZIqM/k7sqCjnPNYB2MymVDO4GyOityFPBOaf5C8YYSHk+q2YzQ0YfrPUuErrKOadUJw7tBlBKSZz45gfTA+ehEkKEPM+pxjQAfcmzAtNfejDZVZEQYUh15sAYpZipdsWxZFKWpNmYX2PHZvdpUYThywCllCdBUte0TRykAinL8txsXGR0aHY6pIUQguvMOQ+r7Wrpb7MAgJREMSkJiZvMTNIO3fw47KOiEFzwVlidXKS5pwQDOUsmVUkIwSb07tw8Hr5Fqe7m7RHVaYk07bamAExJXeglMZXeZeT74/NRhGkqoqq6fz0s3aymsVJKt/SSQG1C72h8fj9Ez8fwWBQirL6ubfSas86w1KHr1AlcUOn2cDT1FovFR286urLQRd4576/ni/ncGw9sdCG7feu1j73r4dBGXbKvnLHnedOxM7DQW0weHp8OT/ujjryodkv0F+u2xrHUSKnbywT9g+GHT5+//Pz1+w8p5wLYRJn1/dCUQhFoVyoXWaCgXN4FFVcEWXy9gtdPRHQRRF/kTgXZRVERERV0ARfUlbI0oUOp6SShzExt0zTtJJmxk9I2zJROSEnaJI30fqFpofdCXb4zLbRpm2ZS9y8UlVx/c+Z/znOeM9PgAbW2Vl16ZWHkmAABBIf9acnxhoYqUIOnuSJvyfSxQZIANTxi3tKsS20dJQ2tDfDGZT8tXTh1dNDQgASPHDUqdHRov/85aur8ZcerS25W2CuabzZkrVg8a9zw370UWh21a8eOfV9/Dcx3H93vK4wf/ObH93749pNvAfq37wVQpwdHvnrukqfUrkviNAqSVGBqinXWXquJnj9GIqqwBWc8tSYHRnJWltKT2dmZhob26LmjAjk5xj3WkneVY1FKZeE4PZlusVgr3WW3LswN8/EhV74q6PXwPq8wZvLDL19oaWxsvLXIO77HP1l8pqHUbihXxaVbXPCNcg0ZpW3nHpvQN4zGPv/Q89Mk4loFyA/v27F+/e5Du79/w2cJPgygC8YC2L/95MCPfw32335fcLEischs1vGsVU9yNE2wPINiRFp+aXPeinESv5oYfbnVbYuNJawWDYYhaj2GcNZYnS2/bWWEWIhPr2vNT3EwqFZLxWQjKGflVCqLnIk/f6mq4UzEgIe3ZFy5kpFSPM77cNfByVFqiud58/le5iPnFXekOHgnpUZYnKVQlGLMvJq12dz2kupZXjCmzR4dFjz2eVHkj288umsXMN+3Y8eOryF7+tb9EOnQ7Prnt4Kt//iMHzMLeuhGkyHz52wLjiA0zVkRnKJw+K3X02q5xpLa9liIZFCFLuvM16oRhuGtCgVpgUhnKcpKw79qrv771rLREj+a3FJKOCkmllEqlVSmi2UoisCyLVY+zaZVlud09H/f4Lyf47ItjpKegzEhuiPBSWIEPBOXyWwL7sT4QzcyrhiMijgFxgFwpVarNWuVFIchMlafVFTxW09ghzwv+TV8dsi0cBHkjx6L2n5Y8JZ9+3bufKsXuW97+fZbyKWfvP9/D0oG06joioyTNuoEqdBzHKBGHTxBEJxGj2Pp6WAXlPZ8y6ABO7Ui1abVchyNozhNkhiNE6CkTIsrW6W6WpTXOWvw7LakVSfnEYdSyfMc53SqEURJsVYLpsZxllXrdIl5Z8f0ZV5Sjqllyo7bnybieKdJS9EKBceyDKO12RZKujTmjOdk5ekk2gLfCEMQCAKcotWYXoZxGC2TqeW660+MlHQp/I+SlSGzR0tni1SJgHzXrl2AfMeuo0KU+4V+oBv6gfe+GWwXI6I+8edsTqllKDDx2LTzZVWFl8oammsLUk1KYE6wCGU2d07zjW1+CudEtAzO6Vmtze12l7VCFs0qLUjIUcVku1QxmUUNT4UMkpRWpCksNMIrteYEY2JqfFlrQ2tVYWG+SZfg1CtImkGtORVgI97ML8mVPGK+FNH93h2VsTiF6PVWTq0m4FxxdzMfX3I1U0FyTjlnTdKZ3fllDWVlYD/2Ai1Dy2gnj/JIXOW50beZD3t91jRJsH/mfzgWJYT5PmAuglzw9M8OQKQLBvPP97/x3XoJayzIySb18M1ji640dxYvmzsjcsaMyOnzXmi5cbkoE1WyCIpqk69N9hmpKXDKUgylPl1U21CzaOa0yRMmT5vxSHRNlpvHXNmQEDlzSvQIn8jPZtlYjcVCyW1mQ3Pnhcfmzo6MnDF77lNnbxVcVcTRCILLrKft7WHezGuSlai6snGcQCu6wZTA8BSGYRC/rszMzJzaBV3IO3Ni1FZ4BePpgoyGtl+enBs5IzIyctaiV1uaPJWxarAZFHUkFId2e8uw1yVzh034o9+C7p2DR3ce3QXQBeRiHawH//W+AB2aAD9A60Xqy46La1VqjsTMyaaG4gX3hgZ5ER09+YWOsmQwG7NS664JH4j82SsuRokomdjaksYnJkp7E0To1DNtyQkqC4KonSq7L+jSF38ymwmFRUO4C68t9H7foNHT/93sxHEUoXDMmFEs9WJ+zobi1sTGCCBb3BzLEiyh5s1p7lJPw82bNxtbnhLqkBaDhiNYTEHYG8/Omzjc64WDxs482+mJN6UlMwhWeqErk87+Y7hk+ITnxfLn9qPbt+8C6ts3ThLd0njmX+91LUaFraP3n5EM1BJPLB9Lsagj6+xEHzVx+KtVWlZIqNzJmgGHbKm53KJHlFqioH1R6IBnvl6XyjJKrTMmt3bFwKM9v8lIsmoXmXnl4szggX53/LpBp1WiGJnb/Cdvb+FIMltgPr7FwGPpcZbMBPvl+lcnjwvtWpPBT2l0iYGgHLEUVVo8wccXuufV6hS3EtOjZvsTEkF/fH7u8/6dZc6xLR99dPTo9l37Du88NkciKim0GT+BEv3AAfCXrwZa+oRrWjPlZHFb9fTBKsFrHvlVudXFnn9Y0ldzSzkF5pLb4ltf8VmdTGuPT7YpY8tVqrLHBnz1lkSw3CTCYF/q2+6nV+elUhSm4Aydw3uZZ1lIMiknb2JEi51FkPT0XEPd2Rl9XmBWYarOSchtZW33DZb1O1N4GtNqNTcn3mYksv5cDcg/2r59+2FA/mhAK9Zv/u89WItCHoVoH7g0erFQq1THZCdlDV5Jj4m+ruLlSU5lW1+y97bFQw5gjQVNc4MGKSNXtsbizqQYznwtsl91etaQTSrI3FNt8wZdZxXnQfbmtYaK+7yYcxQknqv/c9MeizOMnigsntaXWFCNDWpchSv1l8GL1PC8cssJm5aKvxDQYnf1QWAOAnuJem5YYJ0ZaL188sO3PwimPqBKH91yXsnQ2a7mCH8LpuMFDiKJw8se6ZNYiiF/2nhjQXXk4IvbJR5exrK02twe2vd4VWRnn7CSJ9tmSQZHU3zSiqZpzZn/b5hXnANzxio3a50IqrR1/Ll/ppjQhlgx0uK87G9dEF5x2orLzO66iRJxPbrpbx91M4+KWh0c6GDAv97/AZgLnd0D/av0yGo3yiCK67Mk/jS+7aTLFWNJ+9W7WfFwA89SamNi4zR/1rbYrZfRyFX1v1dKvHWmKE7hRIn8RRI/mnaTSEtOZl0lI3uZZ9OoksI4rRlxWe31A996Ub7CpXKdrrpX4k+zKlxxHKIseCGAkD12cEs39KiNq71sQrR4+RzsHDovkEq/6lvpLKhIYGU0e1mk87PousoSR5rbJnpHYRqtoJ2nbs7038Z5pRbBEbWq9mKEd4+jw6nQ87GGthESfzpucCeb1THNE7yYkxhF4YgWJV0nWyZIBuhXN6bKjDGdE0FyJvFnC0txl0aK5sN3Nv2tSx9tObh6zhC6mW9+9b4wZgS2/s8f+9Qu0uNGHUFaTQvEelgNKgttTi70etzSUhtqUTiynpX4V2i9m6lELDFXj3tn3yolLyNSq8Gp/Sm8M4HCZeUpM3qZ/5yeTjAUgzizT9/y4Ychv+UTKgsL6cO/JlZfjcFxRatoc2vO6q1bPt26davA/PEhdX7ffF/oMB4ATz/Qp3aRZgmLfLVnqkRES69aZLZk28VeuylxKtE4MqXeb6R2V0ZKlLO4Ym56ReXZwmQlm5tyQaxRfDaV1is09oe94jxdlWQE5JyherKv1NOeYnQp8KoxYjX0bxkqjLakPiJGbvWmrRDkwBzCfIRkKJryzXsHPoFNDID+3l+lXln+MsMwlBmKJhHNgkBHGa6jpyx7OYOgsHRrDYAU05J8Vo/JLQVP9sZ+g46n1NkVcyUimmtXuID5ot76XE/rNRrcEadrn+2zxmo/xeZqkspEPWNRheuEhXSvlIolUCHGBW3ZNEkyNMHS6IdPII1C8eKdRoPqHALzPFHmYW25JE2pWsPvGPKlWk5Gx1UCR1GNbkvAWFZlKO4BEdHKQt8ksylMIqJpHhKzcPbFvcwJCtdoWNlVOA4+mddo1UajM0uU+YyS7PS4uMpfgkXCfOunn279FIhvOfioZIgKfvMrgP4dLEkh0Ed4MXcm6Ei6VNRbQmsSNTyKld0J64c9OS6FNbckXBKAHrE7tUp9Usf0nrMmn0Ldycp20fJ4aiuNcUb7k17Mcb2G5pWGy6G+W6R1DoxljG2i+yz3lHD69J9zavwXDy9tAuBdzA++I+aDvtzls88/+eEHWJK+9+ODvcyP5yTmkgr3PNFjds7g4lG27I6H1qTKXa5E+xJJIBrbBO3aco1haU+1lK+jbMnuGomYppXhTjmb78WcozE9zaRdGqS4Hdli0FMU0SFqeaObnDT5c2L7KL9hvnbTp38Dfbpl6zHfziLuLlClQ43+mVeva2HBaUs6xqwYJpZzjheclvMJTbfzfPg1HU84U9vCJQHphQJtMk0m1YXceVd7kUptvPq/EjHNKKR4OV/oxZzSYzTFmGoG84QbBhqlyNrFonu/t04nuRL/fcOvvT29dys4C2DfuulpiS+J1y6QQQXm7/3rfq/cqCMVJNV2j0REr99quNbW+NuM226R73TKrfbXJYFp6s1kLYpZGu5E38qWpoaGpo4FEjHNKmMQ3pv5ZRZT0JS5bL5kEEUX6FEqPadxtNiJ+1tjR3Xjjf+M81djr90guDm4i5+aRWQ5+l3XYvTAJz++2RPWETWFWkRPxZ8LEfOHcEFht1301wKLXkbWzpAEppBGG4LrsdKZd14sDF4qbKz4FvWiUkbOU/nezEkFzZgvD3qCzSxVYHoypmBpkMiJOzYsLCw8bGywPz/eu+HTDRs2QHm+d7AEKv3DpPsfuH/SKOkgfy3sXxz4FjpdXrsX0gtVyTjHVp5/YSgzCKEtBgVGkqWjAx2Sf8FN0TRXuFgyNAWdc9N6Nd6HeTow17VIB1+9YXqFqjwpfxFA/y/10t4NHwJzqBYHCfO7/7Lq2B7Q/v2rHrjLd6BD6SIw79N1md1mQyi1EzUVj5EErIlNiRoF4qySBKq5pTI9hxTWD5HDvVVmPUlyA5inHpcMqleuKjA1n5zseQI4/Vcatubtbdu2QZwPEuZ3Pbd/456onTthDmD9zj37H/AVByP++uN7sCctlIvf9JhLyC/xDppTWPlTF+eGSALUPHsiy2rTFkoC1bR8i8XCxtcPDUN4sUdOAnNTX2/BmdQFfuKhrNLKQsNTfuVMpPS/m9sC5iBgvtZXEM9ZtRF2joC4MNh1aP3O/Y/7etSDX8G1AALzA15zXZGXXHEajpNdTa0qfjjQOiQnR2dLht5doApr1cQprGmNYUMxsHmNnpO0K05B9meutfvr0zyWEuOMNTOcs6Dk4qzQ/2Y8cS0w//DDTz/d8I7UVyPmoLBzBOMu6wXou7/+fo+vzekpXx04IAy8wIaR1+TXk7UxMblq1ipz2Etazs6NkIqfdP9OMjqU8bcCJxjSobIo6ISmiQE25cZOmHm8scSeSJTHkRbM7cWcIzHK7PH3OqHF1w2xZplCxZoLmuuip4cH/W7mmwE5MN/7kq/hiy3CIEA3c5iOPvT1epjukg58ka/g6gswl76bdNKXW4synTwC2SohxVN2re2F6RH+xzRHFirKnfLahlHDgno0bFDBg6SjMlScTO8o8bPehYeNDIu4d+qsJ47XdZSVlZ0/71ay5XpZuULhxfySwDytIcKvJV24kuuANRilNCe441vb2l6+LyI46Hcx/6Cb+ZqgAQhWRR0G7QOBucAM4+4vwV++f9AX8x8OCGvRfs3FJ/MSExlKximcsQSfkFBQWtJ5dtHsyaMGAz+qzJoZc1V98mZnu6AbN250/eFbvwm6VKShKT62JNJnqTx22uz5T6280NJSd63JU1BUXs6V0yivVTKIHqddMez5XuZZGj3NmoC5P409Y3fHaiwsw/MEL2O0aZ6GmuhFMyaMlA7Nz3uZBw8c69rezXzXLoC+A6AD8y/XDxzwmtLF/HMwGPAWb01vrFUjLMLTEOu002lMKqqsLPWUXV44PcxXXh1ThV49LbeyhFGn06WZTKbUVIMhVfhzgHS6jBRTWqxT5UKVZtPlGQNcJHzWkjM3m6/XmgSlpZmNSUkaVaZKY1HoXYpyK4pgNO/NnNTjOlNVhMgI7bJCx1WFVU3LcNaJ4HysrsBdCmfwmQX3jQoOPKEIzEEb9r7T/0khx6KObv8IzAWyKBjMboh0uO7i0Lt7HhiYQ+ES6a7rL/qPF419pcyTpqMQTK+nMYzTKxSkXo/hlfbq4mUzBuShiCqb0cjKSAVJknqKYhiKoGmaoii6v6DSSzLCz/RsFaul0qr6dUnGPfx6e7U9R6VSkbSVYpQMhXNWLinJlaRxaVQqTpfGMKwaKfNmTuOs6VqEaJV5yWNKyMWsNIKwVjVHg3CKsBqb235ZNDnA+ix4zR3mA+qWKce2RAkjL6CoKJiqE4oXuLDr6+/f8MH8vc+/g6bL5wPn0cOWtecZ9EAaPhvF42qcwNVqijebUhqaXpkq7bsLUWY2xxLAk8ZxATUDv3EArKf7SaPRJBkJXI/BdLSGppnCmX24HO9IMZmUDA/HCqM5lhC2l+GFOCtrzDFkFFzv+PPCUxTA8u5xCezS6iLEgUXWN2Xk6uF1u8ddETVl1ZO0I/VUfmvV0sBy+Zq3gTmULtventS/EbMRtqSF8Ytd2w++sfrYnqPAHKqX3Tv39w/QZ776/DO4zuif337na6Jr1J8ulpTaU3VmBkVxnICv7uQ4lOLZpMSMW3O9X2tyK4oyTqtczWgZnc4sSAu0CILV9ZXRaDAYzAxDGY05OUaI8+lejb1oj05Nl0N4o/B+BGXUmW3u5Ph4k9uU4impazm7ICJY8iePVdaXOUXraTMwD0BhC5s8+SmpZp5l1RgcVoxWKOTsVQ5jK7PqZwTgMS/dZv7h5v5rolUHYU8amB89HPXAMMmw+98SynTQ13sm9XO5N3/8/LPPgfkP38GayJfCZr54obikoAjslNToCXWMxkkhKHiiLuXWXGkv8zKa5+WxtTCyVlpaUVFRUgJ1hqfUpzweT9dP4TFVN6b1rpJaKkw21ClTU3JOo8nMNdg9VXV1dY3FZ1csnj/1nrAREhAwB6dT/z7mIOk9iy60ZGUUZSpg6N9CWLFyJ6pmOTVTGf9Ty1TxKYse5sslffXOHeZHN3aRfG7Pzh1w2Sgwv7//dNGPcDcAwc8/e2bwc3LM9CXHm5rtqYaCSsfVGDWLU4Adseqyfh3T6y00RxBmz33Th6jIsT3NgMai3Fgthal5nb05ryHvtaUL50WODxs1OkTat2NFWzCkzA9zUeyh9y58rbq51nAywaBjEPg+uJVGGdx5NW+Z2Kp40pEPtoE++GDb2iBfzMFeop6TCPrLxp3rhYJxff8kej9sW3wH0OHmC/f798LQCTMfiy6uyzpldGIKi15t1pqV7sKa8XdSXwONycsdVZLfrfkdpy16mw1TVJ7Kal88IwxI+9TsEms6Sec/JcJclHvErMVn29uy3OakzFwjwTLgZ7TRUzxapHDpZg4/IIkOZA7qYb4HvMUHc0ih4CzCXXWEvqKogkZOnhV9qyG+wEg4GZRCKXP8tfF3mFs5kkz47Xe3M6ZX58BSB42tTLn0wr3+jHV2liYu3SrCPDAFDY+Y9UJLU0ptwUmelRHsCZoqrRGBfuSDdeuEMN+wd45P5od7mcPaaPdA5tK33oUMCu7y3Y9vBkordPJTNy6loVi5wsqqc+23P2N4g1WtT09qD/mdyMMvXlefYGXlGcUv+m8fQJy70k/QZSLMA5c0HIahC9RkdpyCZhnTT6/7z6TLN3+8bh0w/3Dv0/2Z356n29LN/PGd3etRYN7Pzr+A27sI0L96cyjxMT66Sgdj4iqXxlga3V1ylLC0Pt0IHavfpaAX8wkaRRlDi+hEz8wSTXo6JxLnQ1TEkqZKVXo6zhM60+WHRJLo5nXrPgbmG94J6s8coAPyHuaAfN+OAczvF5j/47PP//H5Vw9KhqRx0Q1w9YtFwcV2dFEKqSY4WuEsGS/5XZpYE8/gOK1tGSsR0+wGS3q6XoT5kBX6cKPBilJkttpUHO6343Lk4w/Wfbzugw83gKH3Z94N/ba3RO3btQOw7wTmfTeh/9HN/B9DvhZd+qem2lyFHuNO1Xf958UkNYsRzfdJfpcWljooKJlbIwLZ64AxSU6sVhy6ws+dT6Ys6aQxb6HfM3LNZmD+MVSMYOj9mIO8mG+EHsBA5tI3vxTu8SLctuubOy4WMmLEiJGhoQHMVEeeMzEUojA2RXTvxahRs7zolSGE1siRoaCuN70WK8do4/UFEnEttsPZpQ+Y+fARw0GBXLs+4he3GreSipzGEJFVETDfBsyX92W+qT/z7T6Ywxj6l190M/+ix86bOm8V3/jPr6MC2V27poXGI1Y0TwKaV0mgNiamc1igyO/5T0sLbLL/Z3hXde8kSa6gOlQirmgHiXHq0kCZP3ShuKb+Qj2YtKjGVDsQFHoSMPPrR1Pe7vYWMJcR/ZmDBObD/DB/cP0d5v/qsXPnyYTS/J/qwwKxl/ZSMg6jy493OXJWLKt1KJoD3kKdVZ3oykw883qQ4NFVjFXBAkdxDe9kMRZX2wNl/qe6lLTU1ObFAX2kfBuicMXY5/qv0Nf9/e9C5bLtyBRfzLf0Yb6vP/O3vvwCBMw/673LhZ7Ts7GmzoiAPmNWOYkjrhLBl0a3m7lY3mqaG/C+f0b2z3GqkkckoKcKGUzBFs4IpMRolWM8lWRfHBhz+IwOq4skzgS0dVWjRTGMdq8UMfTbzN9+yQdzGKnrZv44MAf1Y373njvM3+2tzikcozljxXRJABrzW4Jaq4252VVs/OKW5SZRZb8G6ub1GVB/sFXThK/xazyrd9Fl4yTiergAwxgmcOZTS9JkChK7FdCm0KKyWFrGn6/3Xy0Cc0AOzNdI/TD/y23mO/owf/T7L7qZ91gL6CTrxGjC8ERAsVpfiisZffdU6CNuhcuqPF8/LsBt/5o0PYmZu5ZUQfUphF5xoiOQ2ZgWA0cjLBawt4S32NWYXl8W0MJhdnUOwSvPt0tFqkUI9G3b1m0GcxFlvm9XH+ar1n9xSGD+xRde16D/73UdzqA5ZwJalv6m5VCnvKQL87hWBUklm+AKy4C0ohTFWEfCGWk3cyuniGsOIIVOqOIZiiZJW6DMQ+vtavKEvjRSIi4hlxMUk9w+0m8aWwPMIdLXrXt7eR/mn8JUOgwbeTE/DMz7rInu3r8biEOx+O6Xb/USvi/llINCNIFNNNfbZFCh3554vRijR5RpuU0BPRPGzWVWo8H+Z0kX84wkVJbeHECcL3MTjC47XXE+0DWRNDovCabiC6IDqqU8Kj1O2WpG+jeXIwJzoXpZG+LNvOtKAC/mHx0+DBeQ9vHzx7/ffUhg/sW7670WoaM78t0oraldJAlAN+wsJ7c2dNvJrOsWvZxHywIqEaI9FOIkUjvCu5gXFxAUZbkpbkvh1TqcMmpIzB0gc/C8vCRonvGNgRjX5Os/kzRla/TP/G6BedfC6O0pfZgDclBf5jt3RvUyl76x82tgDvryrT94x25hGuEkeRigF1VIe2puEm3J6l6wj6xOIklOmQytRlFNbjvFsGyS/XhQV16ItrMoH5Mnfv4vzSD0FAHMzwfM/J6mIvhcVnsgQTTrisA8tQWg+Z3NFczlYyjSvTcu3tnrk/nhXV7MJ+2BYYCuwmX9GyO84+LSSacVwxwLA7C/YoNCbVU13D4886/EZWNaW8FF0cM1sv2kmSdorvU25afyCZRSZSwRHaCudgBfToPRgTOXFhtOu0jM0TZWIqqnfuIRq95QLLZZBFlUYL5u89q7vJl3Q990m/nBw13MD0f1ushz3wvzXV+8+8Wh9X2K9nGdBqOaVXOt4mf6q5fYdJrIrL5jSyWZFj3CqmpXBIssplb+5HAaWcZxJ1PPLCFYxFVUJ3KwRnemymlBGH4+8H7LvJuGJCuNxr8cJF6/nteiHJkh5o53HXm72102f/zonU8xaS1cDCAg39qX+U6vm7vctf/rL7uYwz3q7u5TAL7WHIvatGyCGAG4j0QqRtJ8wZ97vt2VnKRymVPnecI/8oUep0ZNmJMvTb9zwjTl4jIys3aW/7Oj5hTDUDQQVlND6HGF1KeYY3nK1jpPtPbPcMhQfXaF6NDl8i7mHwDzt0dKgkLumvL02k1wLQBMpXfVLZLbzGGnrmv4YuNzD0y6Syod9uD3Xx8CwQTGbqhavDWx0UYlJ1Os4eII/wjO2k9zmLryUnjP1z+eZ9BwGE6VLZL6Qf5Iq9ylIGnl+V97sDTmUBRmzSwZ4y97vJ7Co0pGB4RxqjBQ5qCHrtmE0Q916wyRWqo6B6MJJLdRdO5+Cqz/BebQSV++fPmatWv37oXZrm7od655mdO9Jx0FFeP2qI3HVq967pnv4f50XwrIv4aqpY+GvVyLnE+mLXj8GX+RPmpFXqITwfHC17186UaKQ2FVYEzZs4Om/hFLCk85LelxJHErvLeXa0AhhEnD2cEP85hz+TyOauMrEQ6YD6WXG9zioHCEMyfX+IUeUXdFhdEYnyeebUcA848/+ECoXTZv3rx3M1wFAD2vD4VQB2+Z050vD360RQhyYL5v186oKGEqffd64TbpcJPX/Xf1L8iadDYlRlLm61nj/WympSTwMp7R9rnuaGbLKadCgckcrS0TBzGkmnyHwxlDZpOlXk4yscOsRNA4lad+sMMcWRPPWuW8tqyMUFhxPnDmoImtZpqlZcrzl/ycf5NvpRIcTbO1NwJo0z398cddFbrQSO8W9AKEQcatcG10N88QuN+IAF3odAF1od91CJjDPN27h74fOGQxvVlOWxGakFd2LPHNIHThzUSCSVbatFV9i43FHk6vZyAcMzqfGO3jSC2rM+l0crWZPVG5pE8SKdQmM3qFMeXGeJ8x+NpNLc/zxtyiP/9PreuEE/cMhTkYNYewFhJtzugcJIrGLL51kkJRhd7409xAZkWFygWYg2BLuou5sF0nXN+16U5afXSjML94FLB3M99xe5oOBtP3+NghWlzLUahTzcpVGTcWhQf13y2fuOxW3ulsklK6tf2v9JKuOMWgqNnGqI1wwCL6PDV0xsrGBh2rJlzlcu3116R9qqVik02GcZgzr/HZ/m84fFp0R2IMJmNir1QslMyyKcpl1iHFOXwquxlXxZXHqIpaXh14u6vgiS+35yVeVaAIZi09G1DXY/mRj4E6QBeob+sWkN+wae+qET23v9gIvAXoEOI90A+B1r/h86qJPIPRaORl6a6cipIz8+4dOTxIKpUGB4eG3zvvtaoyt0nLO2V6Su4Y0Jca/mprAu5k1TSq1BpuNi6EqaDRISPHToyc91rDdUNSEo6wSafL5a2vhvTbAGkxOTEMoXKKaksuzps4OlgqKDh0/PQnqjtSEpxOFqcSmubDuqVUmFcdSpyDQpaV5uaW/5zukp8q7DwDt3WTDusKH+nwkIjIhQ3Np0yG0+lxGK0wnIUTO7BAF2iDrcNPgA6/hCy6d+3yXqceIUDfsgW4C+4iCJhDEt0BYe6znLtm16mVzri49MycopSSxsbXXnttxZnixqaKK06CpZRmSkZajJ6LA70v+OG6giSLBh7DW2IM1/NKGmEQvaaxIaPIFZNusWA0YTyd2PzsgNrg2UsGDqr7ONKVZMho6Kw5u3Lliujizuq8olwV4TQa5bG2zvlde9DyE+WWlB7mw8WZg4IXdpw6nZ1N46xc7ijNunV22ZNPLn7y5bP19TUNVzQWK06Uw7CF0x4gcnB0ATrk0b+vu418W9e07tN39bkV97GDB7fA0KgQ6behH4JhusclvjWjxuxU2hArilKU2eFIKEhNdVTazLGnM1k5yuKEvlzh7Hg2xHc2KlApnEoUxVlKa7OZdToDKMHIUzgus2hggLd15jAfNwlslpM8vDScJTpdaqoJlJyc5jarSVIdqzM6U2/d2z3fctVCxpQOjTlo5m9uJ6KkeAT4JqSm2u1ut/s8XLkRK2cpBOUJtcKSU7co4MszR0B3EfIoSDD0baANG/aumdR/1G71xi2HD0PBuLMr2ruuBbhzjVHonEfvvnukxHsnOwzGteNtsQzK4BRiFYaa9SiC4iTJ4awzKTcnsbZz6mDruaU3DaccDjXFIFolhdN6CzzLiuMMhcNE7/mqwrBBFowFpmSUQnDciljprlvGUkrUjMk4Vgfz10u7bWx2FaEgNV7988tGYG4A5iIKO1dlcisRvYLTc2orDcJRFJVZORnFUIwjobKi7l5J4PrDEcHJAflmQW+vPXJk+SQhUwygfjBq48aNUaCdu7purPvGpDv+NGXYlEfnvNQ3Xi802YuSOCshfH8h3oVfOI5ThNFwpbplltRPrXsW5vY1HKUE5hDvgF0PL6LXaHLyGuunDkoluqXETOutVhqn4B+cAikZBOPMeXUXxt+J17pUTXqmF/PGRDWtEe6vKCbp1AuNFUYLDFsKxxKlWHgLOLAsR6sJQ2lj8Qz4QkOBvubI5g3bAPfbR9auWfPSpJDBcsmkv6xatRqwQ4W+a+exVZN6QnOKZMqkOXP6o3viYok9JVXncLJOXM3zSigOk20mT+sZ/zOFoPHPdjbA4LjW5jAzRtZI8LqEVHup5/JiKBsGV8SyOo89/pTZzBMUyzMMAwfN7S5se2F8D4/Zv7Y3F5S0LOvxll8bmxo81b8Fsj8lnfhsdandlGqzaR3gJgRBxDrS4k12T8nFxRNFiPuAOWf52rVrlj/96KS7xCxpOFyP/vhz+/e/8dwDIyRezOHMmDPQJqYtWllfk2W/klhUZMi4Lkze1784f/L/Z+/uXtqGogCA3363kg8hJpEVWjKoA9uHKaNRBH1xMBl72d8mY0ymYy+dHUxBZCvDhz6onVhlOIcVnC1WGrfado21TZOsu3Uj2lhcYZv4cH7k7X6de0LydHLj6aiwUZwty0ksjSWlWuHxXe6PA8nARKEiJWMpvF7zJiW12bEAcbEDy3MczxsptrA8xrLuTssth9b2pMN0dDWV2sVv9IPSEY6LsaMbxepmfH2hwdHxcDgc8nGEw4o65ejqFfpDZ4RbpMOGOmFx0r7AQHj0waOR8GCfQP7zdNg8nNAfHh3HGxoICb1d9pv7Cz4rul4Wq+W/Tm+xIgAAAAAAAAAAAAAAAAAAAAAAANfBQyEzN9W2I8PyPEPZ2jXRDtQGwVDoL9hovyiKQS9tRy3srhZOp9NltLlIkqQoisYXTRGoBcm6261CGLE723WwdfPeO7e9PGlOksvdwuWytQ7zB3HwHA7+kuAPfcyURq9e3zcvTgReK7JUkouKNsLZzXPUazqHLunX9+qisR+xUdLKZU1WmxQNq6x1XZVxQc7ndnLLp18OGsM96Jxfr200lGRRwarVWrV6KpcnLOiMr6IcZyRVPT49UdWMrD30eYxxIe2FTiMzorCn/56dXasVWNSKDlVL1dJ25vAwWRzsRgb7cLMeNi+pJ2ozihKORS4w581CJb+d29lZ3lQa97rNS1aexEwnYzn3M1NSEF1EDukvP79aeLO0FF+JpIoFvxVdwNRj0c2jS/nrkWPptPEpg5hbXN9KTCci803vFuYS8d38/Ssev8nv2Wdvd3FR4/ut6a/lSa/FiHjqw7en2Xg8kVjA500vLj5fX4lueH+F3lidmcnG5+cjHyMrkexc9FOx9rO0c/9JY1v7+LR4D9Um2tbYZLfatDunNqm9pO6mabfJrkmbnp3uffqntbUWrwgKKoIOCDIyWASBkUFAkLtaLoKoXAoIYsW+UIZxZgSP7z7fH1SGmWGtj896npnFrOdpr8ZOGHc4om8vABSF9DZ9tvC49DufTT9OI/X79QHoghnGRdjNcQt3tl/TcTPzaJBZI6xwq9VqSDg/LxQIXKpjnEhE7xA4EYnOhfLZWyvdV8jMM7DGQy5IWXcwqP76imhxbRGP2DXl0i0IhSaIhfIte69rSStk1HPunWdUO41N+HsHvxc/7uDTAO+zEXZoFeq8FFrBkNBQvlQtfdkDs8x82BhAxpAxq1L6vThirmRcn83CXp0RhnPnEcrlC6bpiR9tWP0p4ZB6UKNQ5zMjs3rNckQi8izXY/+rQYUsRDX0yz6XwLD5k3nlpAQaHCaO4bZDvczFhfwcoZDnZunkMIivU/o9ALE+miChVuHG+qOFceZNoT6zUDEhCzgRHWpSOFURkglfCpsg769k5numIc0LAFdlV8j7iYvymb5MyhP1BvhCxaBqmdD42u9Dc0MMajn6dq8QcqPholcY3uVPIVZDNJGJRsNhT3Q7mhzJlq0+WvFBP+Hs92ZePX78Mh2zK8VsTTFp2jU7a2EASQXXYrFoMhmNxVIq/dG7gjE3JHhDrA3Vd4/PHg4nw+GZMZd7Qr9c9dOM/7L2+g0PTlVmYwnDnVi1Mdec2lNBXJwg1Si4zp1wKpOJhQ1MiYkTOMCgv/g2NOd37aT29vYS0WSuHYk9TxZ7ryoUXoCc0syLe0/+WgWdHL9MdVxFZJ5aMIEUO4/x5ohLgLqDYzpJYGv7dmNdTV1D27Lqm1DosMUbTphnhBCqA9erSQYUl+nkozpf0c4zDGOfqjX//OEVXOUj7I2DXQW4d/fnMKBdfRXzivrTdIx5yjy29JheTxIN680R12V903S18BnXO9Z9ToXCslKwsptBgckRqgKIql6eMGlTjRjzMZZ/5IT5Y1Dk5Lq86fbGyouVl650ZlUc9aAKWzvY1bM7YWtpaMgH65/KNaIYAztSfBYjVHj2t/L6ZIot8mQriMyjENXO6TEda+Mp/vKBfXFhCtxvxd1Ay54FRvmyH1U48z0JyhU4tp6SkkxIXbkk+2PBYlxRuWHwqA44n2jdXi6qasVf178J/eg4yUghSbWXy7Pl6jd0ETY0rzk4GvCwopD5zDXED96kLHHXKmR/YeP5yyxPqKrA30qhZhhce4ZvqLz7XSoNdWK+RT8hPaoGSunicR8KJZvx11cnQ4dtAEH1YbXQQGEet8o3cDtvyhjnF2zLdGKQfeMxLjB83TjzNFvHg9SDCUKouK3XunM+YDRVZL4q1Fri52VekXDrZtaIXaqlAyfMOVvlmCe0sP13Unz3CDiyROGi6v7X6TE7qbge7W/NAJL4BWM6aeWhOPOamNWIyiIkNI2bx6+rMOY2wUSZ7lwKSSDtMIloLUBhTvUt9BXrrBL35+MBFiqhpJat+qCc2mWuNeLOaJFvdnP8fcu4TTTsS0y9ftbUVPSEucCycm7m36cZS8HKMplXptXfyjGPKvhk5sAbmdstvVPoWFIxukSqTHjZ4/5sLba6ctw6r8OZP9wZG+VG2wCSKvPuA2O+4Fot3Z2GkBFyUTIhUpjPQUoK87R1bKZo59eOBiHXqZwh9KCT3x99ijOX88yyHRjeKUYo2p+WXt2OaHRKhzP3QCzk3HZO+z5tngnSSzNPDn20lWOegniFIYqr1avjhrF2/enYHfM+IEZQL8+11A7gdj6P23ntvqjfGS6R8QNnPs9L00szP5j9qIvRzmAehczgHTLQPTay8aJoJqDOJO0GqLrjhbWWFXqROQpxX7y0SgSZBiwEpjgupOe5eJTIHJ2N08/LfGXQtah8VlGSudfk9pZjnoRY1j8olbkWjcnHeNW2XvioihBBRTxjjF6K+c2YzMVeo5/BHOLZS5tQTYS5e2ZWvvo9GAlS7PwHk1G8bqkNWczu6JXT5x3eESqKI68uiELwvXqfU6IsZMapW5OgrnDznQ0jf7t4rEqoY/44L3OgU6qFkdT7lhLWci0lZKjKM8dqSOG69W3M2lPs4OGEmuM98Rc3M1q0rxsgM8fzu3C9T4EzmAtd6RqgpDbtjHmd/X0TrSxzDWyg2LkqIHdidn45yuZqVkoc3NUnnJN2Fu3c/DHQATweQYzJ24WsZzoEfALctRsFiaKd69VcLHvoedR0lGQb+2Vb8XtN1VTmHr7Tfq+cP4cWDGTmq/3y2UxzEXJyek4yfnJt9VU4+OMqgTnPhDGvXFfyGam2M5kLomWYt61ZUJSLpNY6r1aUZL6tmDOJRqIjPfoRTH07nwcCL7FG+pyw7FmpRAhh1pzsA63APIN+3HkEVESYU/DqpZxnScBT4kgl0GHXKb6fMHd/dvWtqnoMIyPDOY2oXp1l9R3jBmTWKmZbkkcr90gWc23bxZ/1po6CRzml05lM4gdu9fSEQE6OoW12RKeMVBVj87YfMv5owi/JtL2yZaAU89q4dUAYrTuTuduRPPLlmnB0lJ9xSROK7ubygKghiIss+dLvWy+XYK4eGjLBDLP7Z1EiHk8nQRhmHhfjfNfr6rc9KOVVM/OswJfKAnMfz6S8n69chMC2bqDqEOQjwZz5tEdhThL352qWn2WeHYPmIBTVoibIZPlwASiv+we+mSUx38zRyqSZ8dtVJ8wTMNfMFUAmWCMQzkMQRyHdv4LfQkvkuVCEq7p9cknODZ94ooc7Zj6e+KgTFJqSN0syv5Rgo25VzZnMOYOaQXRqdFGjVQtRGAU3gaKqXnks8PyCWS7X6SyZDzcqqL5FODekQ5BZ+ZQ8p4WpRQkbNvMcWMMfgDq+t9RArleZzbOh6kJPUzzIdj+/tw9hb//yRCVZtD/4OQ+kmN7CmSu4LpSPzEJDkECgVXDmONJIDXCGGl+PhxG+Tgs72RtK3/r1E+aaBVQohCAYFggX5iGhFoy0FZkfLY7O9mDVTe7ce5HY+hRgW4YrT5r9w8m1Yvei1XEnFz6iEZnPF5k3JJDc35VnMDcsmBkOeEo+NqYRcHh8CR88PjnVxRvLewbLhAtd0I0izuh4E4W5wIRujNgLWloy2FXf2J/RXYz53W98tK8k8xTPyDwoMp9HDXnmtAhTZ7F8dfI3vlTkmW+pT5ivClGuwBIMghabd0uvt9m88f9cOHvpVePj4VjQAIrYyKhTFL+J+xaYYQyA32wejyecl2f/uB6fnhsblc+GvSOplDS3atLh6N3ti5Hq0f6h1PXHCv+i1i2GC59/oTKPsxfUiZozmTN2bfkSQLFEIhyORqPxLoAgWtPj/XjU1je7OMAyJ9eukthFBR/h4addXV2//1bQs5dJ3QL7RTHq84SOJyXzE86PBccrycyBK2nuZzeHwS3kvmy35ZhfKTI3zet2Ht5tP9Gvlf99AR/9xu/ZI5uj16z7lG7EmEf5/RsvW24QVA/gzOUDA3KJ2Mtma/woCktkquPOKlIEzuj4toJTW3HA4gMsplCvW2r2xWa1p+5M5hzZnV+Irbh46suOm93ZlMiFQp83IrUk5kI3Qk4AT9cbp5yYP2/2CkyO9xdLxLgd01iw+wLGHIJVHYV5Ia+ZZXJ9ewIUmSdxO5//vOip+ScLJy8/3pZy5yEv9mnXPIJFe3u5UtV83uiieGmJuSFim3kDTtFDOgXEpMQl227K+66MZnekGyAxXygyrxhXLphs189kbhL99+7Qrr6ISbgQGuwkMvdBPC+2AXeKyJQYY06PT6gHM/QSeVKdPOdIO1BkrtUXmNPGN6YYyuXK4myuOnrCHJ1N1wH/SLVvAyx/32FtgXnYbFbeK7NjXDAvN/z5n7e57CTDfYEpRuAWQFGrDxZ8zdtEN9PFTl+jMMfv/X8LM4TfHp/JnJeiA+dQw/oGizUzeZHInMfboDAf7kOUGPMLH2RqreG0VV1NswVIcbTXJTlF5kBTKOU9uAZgzFFB9ArOXC7epwP/TFWgmxGIN2G+BZ3fKGfnCcX87BpmFiHDopl7KndkdQhhafS1QG1IvAgSSFCYt0W17k+x2rOYD8TO152GIEtt3Ksj3fvPhynM9zesTIw50Lal4DNP2Sftzw2JUTJMKzKfU+gfFScUNzfbgSJzORzDmUMM5T9mDrwKGMUr1zHfwuWmyjFPqk3IeNFHru8OmQJxKrdHG3NqTxtwx4uM2VuBU8wrsYNHdhWwobM8cxsfjl063zLsvyXQRPwSiTmDynxvdgyfKKral8GI8j2NkpXGJ+lHwq1Akfm0QlVkDtTgXq7dzicwN7nA8zO/coN8+/lCZOyPtWB2Dkt8ZZnPmUQRfDB+56Bc6V80qtmZpi1vq3ucoxuhajJz5YK5yBx4Bkp0Eqz1uC42XsKZw7K90t2puEa+IL/4ymEizfvW2+fNdqpvCYxan+GzWZ4JE8f2lNTwtr1Bt4u5fPGEOcNXonRHO4iiqzhzoabn3MzvH8a+NBHHlUdn7t9rwJizA6vlmKfmWNYv+Mu7nt3eXfsjgKw3XxXCwPPZRaGtA6Aw50HeInN6VqnjONavklzc21C2DWPuFUyUnj6i/Z3xvK8n2TBrDt6vITAPm3g+agxl6JQ48wvLUv9HV+pt7clJO7dlbs6nH434AVsml70E87veBU6myDzoH/yaOSfzyuMe2Uy6k/CYxDdG7nqLht0BG9n2cjFUP61mfyHk7AT9XGv6F0osOhpkzbsW5X5K5vfKDxvoEFiBG1YQ4fRaVm4TDoyAbG+ksEOX0uTXEzgSiMYHTc4Qofjns+SQSfyBuEdyCLJRmMdhxs5TgnuXmqDPgaOHl2k/u9WaNsAcrSh9+2SPpJpn6Chh533+XjyGBXt7ObJbTc1XmzHl/moq5wGPtyZ6OdKjJ8157FXNr3a4LnmwHet5mMULPG8h6xLG/Lt6eiJECJiTUhe3N9NIdhDLIiE/d88ueglQ7FxsRgnfh76xS/xCxLDWSqflS4W3jNgRnZF5XNjhaWB62n+r5fr1lrywnz/funQohY1MX+ZJU77qd03LsIXDkqevE5lv+XuTFOYrFon3GcEB7tt0fhYnkFkff/XhIGZAjDyXKNZBHBi93NSjEsxTPIUev1bcdc/vWrxRT8aztbWV3N7ei4Wy5WLU9fWvCjcHTiZCkS/r6e8ajrnfMFmNMff6oY+7O/ptT07b29ueLemWHrsTrc0opr+OE78IOuhzT09sVpCjUdTVb3SKY81U5jPyqSDtxC//4XPyeHKrN3MQCh0kLNxdLlecvon5FunQR5PYt53QJ7dyXdnLtWYv8q7Q7QMQceb80lr2MNf4pKPX5PS9JX+D2PtV9RslT7W3T9VN3OfdKmLudWtkNhD0ipB+RGKL3yRdFQfEwVL+XAVr8Lnc0KexsTGrRMSe0MACPixBxErlyGZtueurv5KD5gWZFLQx84XT+f32yOVieI316/gwu88iQjQaCYLM6lC/dLwTi/gTDv0mQNCNhEYhW79OhhsCRWw2uEyjMg+KmSHCRlrHNts1sIiIRRabdEKLfraq8CqqXXo/NGC1Io5BBSyeWZoRSySWnsP6QgvHtwYVnF32hldlk3E4bskI+bG4mkiyZ72d/Nmbw6vrj0hb2g/CFo1WoJU5ZTlWhuD4ZdLbkR5fqK1UwRZmT7YYTd5Gl+xLBhCU5lghYnGOuNKwnS3HHKDdXFGlQBDsC1itSqZv7/c6fFRFfEyvgRkG89XtxcqlGauErT/8teA2snr9ShdAVOe2FMzeoNxEB8E+Z+w2QNHrUFD1mjQH1BKPKpUSCazR5EtbG0JdeCvu74P2GfsS06JxiJfyUor7MsXu1N6Je8PMWUmf9KtMqwFDHdXUrJ4HVGtry57aVPfocNsSgCUStnf1YPkGxUJaswfvqkpwe3eQfYQPls3jbCSbPTw8zOaU/33w48yqzLTGR5GDeEYVi60fkx4+a9uMfPgy+eXLl+Xl8cnc78nJ8c37GKqmbIRSzI32ev/gXSXlFmsy+o0ZIjocrIkR6gONFb9E9jzeHQvoje5lf2sknKJrM9+C8eHh8XxT8q2YfHeNcL14fzOd2c4pvt/ZAFBVc5l2alMDrcS0x7+ef4Q/PX/YTAeA0weUKZJK/98yTlU05ELuZToNOLcunB45l+oBqqpv/fthNXBapQoeXmr51/N/P394q6ni/ztj0dTS0txQS2z8/wEYmdN8sk+R0QAAAABJRU5ErkJggg=="
        logo_section = f"""
        <div style="text-align: center; padding: 25px 20px; background-color: #ffffff; border-bottom: 1px solid #e0e0e0;">
            <!-- Sears Home Services Logo -->
            <img src="data:image/png;base64,{logo_base64}" alt="Sears Home Services" style="max-width: 200px; height: auto;" />
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BYOV Enrollment Notification</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f7fa;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            {logo_section}
            
            <!-- Header Banner -->
            <div style="background-color: #e8f4fc; padding: 20px; text-align: center; border-bottom: 3px solid #0d6efd;">
                <h2 style="color: #0d6efd; margin: 0; font-size: 22px;">
                    New BYOV Enrollment Submitted
                </h2>
                <p style="color: #666; margin: 10px 0 0 0; font-size: 14px;">
                    Submitted on {submission_date}
                </p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                
                <!-- Technician Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #0d6efd; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #0d6efd; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        👤 Technician Information
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Name:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Tech ID:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('tech_id', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">District:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('district', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">State:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('state', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Referred By:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('referred_by', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Industries:</td>
                            <td style="padding: 8px 0; color: #333;">{industries_str}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Vehicle Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #28a745; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #28a745; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        🚗 Vehicle Information
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Year:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('year', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Make:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('make', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Model:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('model', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">VIN:</td>
                            <td style="padding: 8px 0; color: #333; font-family: monospace;">{record.get('vin', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Documentation Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #ffc107; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #856404; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        📋 Documentation
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Insurance Exp:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('insurance_exp', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Registration Exp:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('registration_exp', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Template Used:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('template_used', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Files Summary -->
                <div style="background: #f8f9fa; border-radius: 8px; padding: 15px; margin-bottom: 20px; text-align: center;">
                    <p style="margin: 0; color: #666; font-size: 14px;">
                        <strong>Files Uploaded:</strong>
                        Vehicle Photos: {len(record.get('vehicle_photos_paths', [])) if record.get('vehicle_photos_paths') else 0} |
                        Insurance: {len(record.get('insurance_docs_paths', [])) if record.get('insurance_docs_paths') else 0} |
                        Registration: {len(record.get('registration_docs_paths', [])) if record.get('registration_docs_paths') else 0}
                    </p>
                </div>
                
                <!-- Notes -->
                {"" if not record.get('comment') else f'''
                <div style="background: #fff3cd; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                    <h4 style="color: #856404; margin: 0 0 10px 0; font-size: 14px;">📝 Additional Notes:</h4>
                    <p style="margin: 0; color: #333; font-size: 14px;">{record.get("comment", "")}</p>
                </div>
                '''}
                
            </div>
            
            <!-- Footer -->
            <div style="background-color: #2c3e50; padding: 20px; text-align: center;">
                <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 12px;">
                    This is an automated notification from the BYOV Enrollment System
                </p>
                <p style="color: rgba(255,255,255,0.6); margin: 10px 0 0 0; font-size: 11px;">
                    Sears Home Services | BYOV Program
                </p>
            </div>
            
        </div>
    </body>
    </html>
    """
    
    return html


def get_plain_text_body(record):
    """Generate plain text email body as fallback."""
    industries_list = record.get('industry', record.get('industries', []))
    industries_str = ", ".join(industries_list) if industries_list else "None"
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y")
        except Exception:
            pass
    
    return f"""
SEARS HOME SERVICES - BYOV Enrollment System
=============================================

A new BYOV enrollment has been submitted.

TECHNICIAN INFORMATION
----------------------
Name:               {record.get('full_name','')}
Tech ID:            {record.get('tech_id','')}
District:           {record.get('district','')}
State:              {record.get('state', 'N/A')}
Referred By:        {record.get('referred_by', '')}
Industries:         {industries_str}

VEHICLE INFORMATION
-------------------
Year:               {record.get('year','')}
Make:               {record.get('make','')}
Model:              {record.get('model','')}
VIN:                {record.get('vin','')}

DOCUMENTATION
-------------
Insurance Exp:      {record.get('insurance_exp','')}
Registration Exp:   {record.get('registration_exp','')}
Template Used:      {record.get('template_used', 'N/A')}

FILES UPLOADED
--------------
Vehicle Photos:         {len(record.get('vehicle_photos_paths', [])) if record.get('vehicle_photos_paths') else 0} files
Insurance Documents:    {len(record.get('insurance_docs_paths', [])) if record.get('insurance_docs_paths') else 0} files
Registration Documents: {len(record.get('registration_docs_paths', [])) if record.get('registration_docs_paths') else 0} files

ADDITIONAL NOTES
----------------
{record.get('comment', 'None')}

Submitted: {submission_date}

Files are attached to this email when feasible. If the files are too large,
they are available via the BYOV Admin Dashboard.

This is an automated notification from the BYOV Enrollment System.
"""


def send_email_notification(record, recipients=None, subject=None, attach_pdf_only=False):
    """Send an email notification about an enrollment record.

    This function mirrors the email behavior used by the main app but is
    contained in a separate module so it can be invoked from other tools
    (admin dashboard, cron jobs, etc.).
    
    Args:
        record: Enrollment record dictionary
        recipients: Email recipient(s) - string or list
        subject: Custom subject line
        attach_pdf_only: If True, only attach the signed PDF (for HR emails)
    
    Returns True on success, False otherwise.
    """
    email_config = st.secrets.get("email", {})

    sender = email_config.get("sender")
    app_password = email_config.get("app_password")
    default_recipient = email_config.get("recipient")

    if recipients:
        if isinstance(recipients, str):
            recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
        elif isinstance(recipients, (list, tuple)):
            recipient_list = [r for r in recipients if r]
        else:
            recipient_list = [str(recipients)]
    else:
        recipient_list = [default_recipient] if default_recipient else []

    subject = subject or f"New BYOV Enrollment: {record.get('full_name','Unknown')} (Tech {record.get('tech_id','N/A')})"

    html_body = get_sears_html_template(record)
    plain_body = get_plain_text_body(record)

    msg = MIMEMultipart('alternative')
    msg["From"] = sender or os.getenv("SENDGRID_FROM_EMAIL") or "no-reply@shs.com"
    msg["To"] = ", ".join(recipient_list) if recipient_list else ""
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    files = []
    
    if attach_pdf_only:
        pdf_path = record.get('signature_pdf_path')
        if pdf_path:
            if file_storage.file_exists(pdf_path):
                files.append(pdf_path)
    else:
        file_keys = [
            'signature_pdf_path',
            'vehicle_photos_paths',
            'insurance_docs_paths',
            'registration_docs_paths'
        ]
        for k in file_keys:
            v = record.get(k)
            if not v:
                continue
            if isinstance(v, list):
                for p in v:
                    if p and file_storage.file_exists(p):
                        files.append(p)
            else:
                if isinstance(v, str) and file_storage.file_exists(v):
                    files.append(v)

    try:
        MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024

        def get_file_size(path):
            try:
                if file_storage.is_object_storage_path(path):
                    content = file_storage.read_file(path)
                    return len(content) if content else 0
                return os.path.getsize(path)
            except Exception:
                return 0

        total_size = sum(get_file_size(p) for p in files) if files else 0

        if files and total_size > MAX_ATTACHMENT_SIZE:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for p in files:
                    arcname = os.path.basename(p)
                    try:
                        content = file_storage.read_file(p)
                        if content:
                            zf.writestr(arcname, content)
                    except Exception:
                        pass
            zip_buffer.seek(0)
            zipped_size = len(zip_buffer.getvalue())
            if zipped_size <= MAX_ATTACHMENT_SIZE:
                part = MIMEApplication(zip_buffer.read())
                part.add_header('Content-Disposition', 'attachment', filename='enrollment_files.zip')
                msg.attach(part)
        else:
            for p in files:
                try:
                    content = file_storage.read_file(p)
                    if content:
                        ctype, encoding = mimetypes.guess_type(p)
                        if ctype is None:
                            ctype = 'application/octet-stream'
                        maintype, subtype = ctype.split('/', 1)
                        part = MIMEApplication(content, _subtype=subtype)
                        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(p))
                        msg.attach(part)
                except Exception:
                    continue

        sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
        sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL") or sender
        
        if sg_key and sg_from and recipient_list:
            try:
                sg_payload = {
                    "personalizations": [{"to": [{"email": r} for r in recipient_list]}],
                    "from": {"email": sg_from, "name": "Sears Home Services BYOV"},
                    "subject": subject,
                    "content": [
                        {"type": "text/plain", "value": plain_body},
                        {"type": "text/html", "value": html_body}
                    ]
                }
                
                attachments = []
                for p in files:
                    try:
                        content = file_storage.read_file(p)
                        if content:
                            ctype, _ = mimetypes.guess_type(p)
                            if ctype is None:
                                ctype = 'application/octet-stream'
                            attachments.append({
                                "content": base64.b64encode(content).decode('utf-8'),
                                "filename": os.path.basename(p),
                                "type": ctype,
                                "disposition": "attachment"
                            })
                    except Exception:
                        pass
                
                if attachments:
                    sg_payload["attachments"] = attachments
                
                resp = requests.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {sg_key}",
                        "Content-Type": "application/json"
                    },
                    data=json.dumps(sg_payload),
                    timeout=30
                )
                
                if 200 <= resp.status_code < 300:
                    return True
                else:
                    st.warning(f"SendGrid failed ({resp.status_code}); falling back to SMTP if configured.")
            except Exception as e:
                st.warning(f"SendGrid error: {e}; falling back to SMTP if configured.")

        if not sender or not app_password or not recipient_list:
            if not sg_key:
                st.warning("Email credentials not fully configured. Please set up SendGrid API key or Gmail SMTP credentials.")
            return False

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, recipient_list, msg.as_string())
        return True
        
    except Exception as e:
        st.error(f"Email sending failed: {str(e)}")
        return False


def send_pdf_to_hr(record, hr_email, custom_subject=None):
    """Send the signed PDF to HR with a custom recipient.
    
    Args:
        record: Enrollment record dictionary (must include signature_pdf_path)
        hr_email: HR email address to send to
        custom_subject: Optional custom subject line
    
    Returns True on success, False otherwise.
    """
    if not hr_email:
        st.error("Please enter an HR email address.")
        return False
    
    subject = custom_subject or f"BYOV Signed Agreement - {record.get('full_name', 'Unknown')} (Tech ID: {record.get('tech_id', 'N/A')})"
    
    return send_email_notification(
        record,
        recipients=hr_email,
        subject=subject,
        attach_pdf_only=True
    )


def get_email_config_status():
    """Get the current email configuration status for display."""
    email_config = st.secrets.get("email", {})
    
    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    gmail_sender = email_config.get("sender")
    gmail_password = email_config.get("app_password")
    
    status = {
        "sendgrid_configured": bool(sg_key and sg_from),
        "sendgrid_from": sg_from or "Not configured",
        "gmail_configured": bool(gmail_sender and gmail_password),
        "gmail_sender": gmail_sender or "Not configured",
        "primary_method": "SendGrid" if sg_key else ("Gmail SMTP" if gmail_sender else "Not configured")
    }
    
    return status
