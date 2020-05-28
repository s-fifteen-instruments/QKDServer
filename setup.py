import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='S15QKD',
    version='0.1',
    description='S-Fifteen QKD process controller python library',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://s-fifteen.com/',
    author='https://s-fifteen.com/',
    author_email='',
    license='MIT',
    packages=setuptools.find_packages(),
    install_requires=[],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Linux",
    ]
)
