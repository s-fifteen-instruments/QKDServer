import setuptools
import os
from Cython.Build import cythonize
import numpy as np


with open("README.md", "r") as fh:
    long_description = fh.read()

here = os.path.dirname(__file__)

extensions = [
    setuptools.Extension(
        "S15qkd.g2lib.delta",
        [os.path.join(here, "S15qkd", "g2lib", "delta.pyx")],
        include_dirs=[np.get_include()],
    ),
]

setuptools.setup(
    name='S15qkd',
    version='0.1',
    description='S-Fifteen QKD process controller python library',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://s-fifteen.com/',
    author='https://s-fifteen.com/',
    author_email='',
    license='MIT',
    packages=setuptools.find_packages(),
    install_requires=['Cython', 'numpy'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Linux",
    ],
    ext_modules=cythonize(extensions)
)
